import asyncio
import json
import os
import queue
import re
import shutil
import threading
import urllib.request
import uuid
from pathlib import Path

import numpy as np
import ollama
import soundfile as sf
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from kokoro_onnx import Kokoro

VOICE_NAME = "af_sky"

PROJECT_ROOT = Path(__file__).parent.parent
KOKORO_MODEL = PROJECT_ROOT / "models" / "kokoro-v1.0.onnx"
VOICES_BIN = PROJECT_ROOT / "models" / "voices-v1.0.bin"

DEFAULT_OUT_BASE = Path.home() / "MakeDocTalk" / "docs"
DEFAULT_OUT_BASE.mkdir(parents=True, exist_ok=True)

KOKORO_DOWNLOADS = [
    (
        "kokoro-v1.0.onnx",
        KOKORO_MODEL,
        "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx",
    ),
    (
        "voices-v1.0.bin",
        VOICES_BIN,
        "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin",
    ),
]

_pdf_pipeline_options = PdfPipelineOptions(
    do_ocr=True,
    do_table_structure=False,
    do_code_enrichment=False,
    do_formula_enrichment=False,
    generate_page_images=False,
    generate_picture_images=False,
)
_converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=_pdf_pipeline_options)
    }
)

app = FastAPI(title="PDF-to-Speech API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job registry: job_id -> {"out_dir": Path, "doc_name": str}
_jobs: dict[str, dict] = {}


def _get_job_dir(job_id: str) -> Path:
    if job_id in _jobs:
        d = _jobs[job_id]["out_dir"]
    else:
        d = DEFAULT_OUT_BASE / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_doc_name(job_id: str) -> str:
    if job_id in _jobs:
        return _jobs[job_id]["doc_name"]
    return job_id


def _require_file(path: Path, label: str):
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"{label} not found at {path}. Run the previous stage first.",
        )


def _split_text_smart(text, max_len=400):
    """Smart text splitter — splits on punctuation, then commas, then words."""
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"([.!?]+)", text)
    sentences, current = [], ""
    for part in parts:
        if re.match(r"^[.!?]+$", part):
            current += part
            sentences.append(current.strip())
            current = ""
        else:
            current += part
    if current.strip():
        sentences.append(current.strip())

    final_chunks = []
    for sent in sentences:
        if not sent.strip():
            continue
        if len(sent) <= max_len:
            final_chunks.append(sent)
        else:
            sub_parts = re.split(r"([,;:]+)", sent)
            current_sub = ""
            for sub in sub_parts:
                if len(current_sub) + len(sub) <= max_len:
                    current_sub += sub
                else:
                    if current_sub.strip():
                        final_chunks.append(current_sub.strip())
                    current_sub = sub
            if current_sub.strip():
                final_chunks.append(current_sub.strip())

    really_final = []
    for chunk in final_chunks:
        if len(chunk) <= max_len:
            really_final.append(chunk)
        else:
            words = chunk.split(" ")
            cur = ""
            for word in words:
                if len(cur) + len(word) + 1 <= max_len:
                    cur += word + " "
                else:
                    if cur.strip():
                        really_final.append(cur.strip())
                    cur = word + " "
            if cur.strip():
                really_final.append(cur.strip())
    return really_final


# ---------------------------------------------------------------------------
# Stage 1 — Extract
# ---------------------------------------------------------------------------


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.post("/jobs/{job_id}/extract")
async def extract(job_id: str, pdf: UploadFile = File(...)):
    """
    Upload a PDF and extract its text with Docling.
    Streams SSE progress events, then a final 'done' event with results.
    """

    async def event_stream():
        job_dir = _get_job_dir(job_id)
        doc_name = _get_doc_name(job_id)

        yield _sse({"status": "saving", "message": "Saving PDF..."})
        pdf_path = job_dir / f"{doc_name}.pdf"
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(pdf.file, f)

        yield _sse(
            {
                "status": "extracting",
                "message": "Extracting text with Docling (this may take a while)...",
            }
        )
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _converter.convert, str(pdf_path))
        text = result.document.export_to_markdown()

        yield _sse({"status": "writing", "message": "Writing output file..."})
        out_path = job_dir / f"{doc_name}_extracted.md"
        out_path.write_text(text, encoding="utf-8")

        yield _sse(
            {
                "status": "done",
                "job_id": job_id,
                "stage": "extract",
                "output_file": str(out_path),
                "char_count": len(text),
            }
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/jobs/extract")
async def extract_new_job(pdf: UploadFile = File(...), out_dir: str = Form("")):
    """
    Convenience endpoint: creates a new job ID automatically, then runs extraction.
    Accepts an optional `out_dir` form field (absolute or ~/... path).
    Defaults to ~/MakeDocTalk/docs/<pdf_stem>/.
    Streams the same SSE events as /jobs/{job_id}/extract.
    """
    job_id = str(uuid.uuid4())

    pdf_stem = Path(pdf.filename).stem if pdf.filename else "document"

    if out_dir and out_dir.strip():
        job_out_dir = Path(out_dir.strip()).expanduser().resolve()
    else:
        job_out_dir = DEFAULT_OUT_BASE / pdf_stem

    doc_name = job_out_dir.name

    _jobs[job_id] = {"out_dir": job_out_dir, "doc_name": doc_name}

    response = await extract(job_id, pdf)
    return response


# ---------------------------------------------------------------------------
# Stage 2 — Refine
# ---------------------------------------------------------------------------


@app.post("/jobs/{job_id}/refine")
async def refine(job_id: str):
    """
    Clean the extracted text with Ollama LLM (removes citations, page numbers, etc.).
    Streams SSE progress events with chunk counts, then a final 'done' event.
    Requires stage 1 to have been run first.
    """

    async def event_stream():
        job_dir = _get_job_dir(job_id)
        doc_name = _get_doc_name(job_id)
        in_path = job_dir / f"{doc_name}_extracted.md"
        _require_file(in_path, f"{doc_name}_extracted.md")

        raw = in_path.read_text(encoding="utf-8")

        try:
            llm_model = _pick_llm_model()
        except RuntimeError as e:
            yield _sse({"status": "error", "message": str(e)})
            return

        chunks = _split_text_smart(raw, max_len=800)
        total = len(chunks)
        cleaned_chunks = []

        yield _sse(
            {
                "status": "refining",
                "message": f"Refining {total} chunks...",
                "total": total,
                "completed": 0,
            }
        )

        loop = asyncio.get_event_loop()

        for idx, chunk in enumerate(chunks, start=1):

            def call_ollama(c=chunk, m=llm_model):
                return ollama.chat(
                    model=m,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a professional editor. Remove citations, page numbers, "
                                "and image captions. Join words split by hyphens. Do not change "
                                "the content. Retain headers. Do not add any text."
                            ),
                        },
                        {"role": "user", "content": f"Clean this for TTS: \n\n{c}"},
                    ],
                )

            try:
                response = await loop.run_in_executor(None, call_ollama)
                cleaned_chunks.append(response["message"]["content"])
            except Exception:
                cleaned_chunks.append(chunk)

            yield _sse(
                {
                    "status": "refining",
                    "message": f"Refined chunk {idx}/{total}",
                    "total": total,
                    "completed": idx,
                }
            )

        yield _sse({"status": "writing", "message": "Writing output file..."})
        refined = " ".join(cleaned_chunks)
        out_path = job_dir / f"{doc_name}_refined.txt"
        out_path.write_text(refined, encoding="utf-8")

        yield _sse(
            {
                "status": "done",
                "job_id": job_id,
                "stage": "refine",
                "output_file": str(out_path),
                "char_count": len(refined),
            }
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Stage 3 — TTS
# ---------------------------------------------------------------------------


@app.post("/jobs/{job_id}/tts")
async def tts(job_id: str):
    """
    Generate an audiobook WAV from the refined text using Kokoro TTS.
    Streams SSE progress events, then a final 'done' event with results.
    Requires stage 2 to have been run first.
    """

    async def event_stream():
        job_dir = _get_job_dir(job_id)
        doc_name = _get_doc_name(job_id)
        in_path = job_dir / f"{doc_name}_refined.txt"

        if not in_path.exists():
            yield _sse(
                {
                    "status": "error",
                    "message": f"{doc_name}_refined.txt not found. Run the refine stage first.",
                }
            )
            return

        try:
            text = in_path.read_text(encoding="utf-8")
            chunks = _split_text_smart(text)
            total = len(chunks)

            yield _sse(
                {"status": "loading_model", "message": "Loading Kokoro TTS model..."}
            )

            loop = asyncio.get_event_loop()
            kokoro = await loop.run_in_executor(
                None, lambda: Kokoro(str(KOKORO_MODEL), str(VOICES_BIN))
            )

            yield _sse(
                {
                    "status": "generating",
                    "message": f"Generating audio for {total} chunks...",
                    "total": total,
                    "completed": 0,
                }
            )

            all_samples = []
            sample_rate = None

            def process_chunk(chunk):
                if not chunk.endswith((".", "!", "?", ";", ":")):
                    chunk += "."
                return kokoro.create(chunk, voice=VOICE_NAME, speed=1.0)

            for idx, chunk in enumerate(chunks, start=1):
                if not chunk.strip():
                    continue
                samples, sample_rate = await loop.run_in_executor(
                    None, process_chunk, chunk
                )
                all_samples.append(samples)
                yield _sse(
                    {
                        "status": "generating",
                        "message": f"Chunk {idx}/{total}",
                        "total": total,
                        "completed": idx,
                    }
                )

            if not all_samples:
                yield _sse(
                    {
                        "status": "error",
                        "message": "No audio generated — text may be empty.",
                    }
                )
                return

            yield _sse({"status": "writing", "message": "Writing audio file..."})
            out_path = job_dir / f"{doc_name}_audio.wav"
            await loop.run_in_executor(
                None,
                lambda: sf.write(
                    str(out_path), np.concatenate(all_samples), sample_rate
                ),
            )

            yield _sse(
                {
                    "status": "done",
                    "job_id": job_id,
                    "stage": "tts",
                    "output_file": str(out_path),
                }
            )

        except Exception as e:
            yield _sse({"status": "error", "message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


@app.get("/jobs/{job_id}/audio")
def download_audio(job_id: str):
    """Download the generated audio WAV for a job."""
    job_dir = _get_job_dir(job_id)
    doc_name = _get_doc_name(job_id)
    wav_path = job_dir / f"{doc_name}_audio.wav"
    _require_file(wav_path, f"{doc_name}_audio.wav")
    return FileResponse(
        str(wav_path), media_type="audio/wav", filename=f"{doc_name}_audio.wav"
    )


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    """Return which stages have been completed for a given job."""
    job_dir = _get_job_dir(job_id)
    doc_name = _get_doc_name(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return {
        "job_id": job_id,
        "doc_name": doc_name,
        "out_dir": str(job_dir),
        "stages": {
            "extract": (job_dir / f"{doc_name}_extracted.md").exists(),
            "refine": (job_dir / f"{doc_name}_refined.txt").exists(),
            "tts": (job_dir / f"{doc_name}_audio.wav").exists(),
        },
    }


# ---------------------------------------------------------------------------
# Health / dependency checks
# ---------------------------------------------------------------------------


KNOWN_MODELS = [
    "qwen3:0.6b",
    "qwen3:1.7b",
    "qwen3:4b",
    "llama3.2:1b",
    "llama3.2:3b",
    "llama4:8b",
    "gemma3:1b",
    "gemma3:4b",
    "gemma3:12b",
    "phi3.5:latest",
    "phi4:14b",
    "phi4-mini-instruct",
    "mistral:7b",
    "mistral-small3.2:24b",
    "smollm3:3b",
    "liquid-lfm:1.2b",
    "lfm2.5-thinking:1.2b",
    "granite4:1b",
    "granite4:3b",
    "deepseek-v3.2-exp:7b",
    "ministral-3:3b",
    "ministral-3:8b",
    "glm-4.7-flash",
    "rnj-1:8b",
]


def _pick_llm_model() -> str:
    """Return the first installed KNOWN_MODELS entry, or raise RuntimeError."""
    override = os.environ.get("LLM_MODEL")
    if override:
        return override
    models_response = ollama.list()
    installed_names = [m.model for m in models_response.models]
    for candidate in KNOWN_MODELS:
        if any(candidate in name for name in installed_names):
            return candidate
    raise RuntimeError(
        "No supported Ollama model found. Pull one of: " + ", ".join(KNOWN_MODELS)
    )


@app.get("/health/ollama")
async def health_ollama():
    """Check Ollama connectivity and whether any supported model is available."""
    try:
        loop = asyncio.get_event_loop()
        models_response = await loop.run_in_executor(None, ollama.list)
        installed_names = [m.model for m in models_response.models]
        found = [m for m in KNOWN_MODELS if any(m in name for name in installed_names)]
        if found:
            return {
                "ok": True,
                "found_models": found,
                "detail": f"Found: {', '.join(found)}",
            }
        else:
            return {
                "ok": False,
                "found_models": [],
                "detail": "No supported model found. Pull one of: "
                + ", ".join(KNOWN_MODELS),
            }
    except Exception as e:
        return {"ok": False, "found_models": [], "detail": f"Ollama not reachable: {e}"}


@app.get("/health/kokoro")
async def health_kokoro():
    """Check whether the required Kokoro TTS model files are present."""
    kokoro_model_ok = KOKORO_MODEL.exists()
    voices_ok = VOICES_BIN.exists()
    return {
        "ok": kokoro_model_ok and voices_ok,
        "files": {
            "kokoro-v1.0.onnx": kokoro_model_ok,
            "voices-v1.0.bin": voices_ok,
        },
    }


@app.get("/health")
async def health():
    """Check that all required models and services are installed."""
    ollama_data = await health_ollama()
    kokoro_data = await health_kokoro()
    return {
        "ok": ollama_data["ok"] and kokoro_data["ok"],
        "ollama": ollama_data,
        "kokoro": kokoro_data,
    }


@app.post("/download-kokoro")
async def download_kokoro():
    """Download missing Kokoro model files into the models/ directory. Streams SSE progress."""

    async def event_stream():
        needed = [
            (name, dest, url)
            for name, dest, url in KOKORO_DOWNLOADS
            if not dest.exists()
        ]

        if not needed:
            yield _sse(
                {"status": "done", "message": "All Kokoro files already present."}
            )
            return

        KOKORO_MODEL.parent.mkdir(parents=True, exist_ok=True)

        for filename, dest_path, url in needed:
            yield _sse({"status": "downloading", "file": filename, "percent": 0})

            q: queue.Queue = queue.Queue()

            def do_download(url=url, dest=dest_path, fname=filename):
                tmp = Path(str(dest) + ".tmp")
                try:
                    last_pct = [-1]

                    def reporthook(block_num, block_size, total_size):
                        if total_size > 0:
                            pct = min(
                                int(block_num * block_size * 100 / total_size), 100
                            )
                            if pct != last_pct[0]:
                                last_pct[0] = pct
                                q.put(
                                    {"type": "progress", "file": fname, "percent": pct}
                                )

                    urllib.request.urlretrieve(url, str(tmp), reporthook)
                    tmp.rename(dest)
                    q.put({"type": "done", "file": fname})
                except Exception as e:
                    if tmp.exists():
                        tmp.unlink()
                    q.put({"type": "error", "file": fname, "message": str(e)})

            thread = threading.Thread(target=do_download, daemon=True)
            thread.start()

            while thread.is_alive() or not q.empty():
                try:
                    msg = q.get_nowait()
                    if msg["type"] == "progress":
                        yield _sse(
                            {
                                "status": "downloading",
                                "file": msg["file"],
                                "percent": msg["percent"],
                            }
                        )
                    elif msg["type"] == "done":
                        yield _sse({"status": "file_done", "file": msg["file"]})
                        break
                    elif msg["type"] == "error":
                        yield _sse({"status": "error", "message": msg["message"]})
                        return
                except queue.Empty:
                    await asyncio.sleep(0.1)

        yield _sse(
            {"status": "done", "message": "Kokoro models downloaded successfully."}
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
