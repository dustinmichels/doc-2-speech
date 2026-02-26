import asyncio
import json
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
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from kokoro_onnx import Kokoro

LLM_MODEL = "llama3.2:3b"
VOICE_NAME = "af_sky"

PROJECT_ROOT = Path(__file__).parent.parent
KOKORO_MODEL = PROJECT_ROOT / "models" / "kokoro-v1.0.onnx"
VOICES_BIN = PROJECT_ROOT / "models" / "voices-v1.0.bin"
OUT_DIR = PROJECT_ROOT / "out"

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


def _get_job_dir(job_id: str) -> Path:
    d = OUT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


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

        yield _sse({"status": "saving", "message": "Saving PDF..."})
        pdf_path = job_dir / pdf.filename
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
        out_path = job_dir / "extracted.txt"
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
async def extract_new_job(pdf: UploadFile = File(...)):
    """
    Convenience endpoint: creates a new job ID automatically, then runs extraction.
    Streams the same SSE events as /jobs/{job_id}/extract.
    """
    job_id = str(uuid.uuid4())
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
        in_path = job_dir / "extracted.txt"
        _require_file(in_path, "extracted.txt")

        raw = in_path.read_text(encoding="utf-8")

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

            def call_ollama(c=chunk):
                return ollama.chat(
                    model=LLM_MODEL,
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
        out_path = job_dir / "refined.txt"
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
        in_path = job_dir / "refined.txt"

        if not in_path.exists():
            yield _sse(
                {
                    "status": "error",
                    "message": "refined.txt not found. Run the refine stage first.",
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
            out_path = job_dir / "audiobook.wav"
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
    """Download the generated audiobook WAV for a job."""
    wav_path = OUT_DIR / job_id / "audiobook.wav"
    _require_file(wav_path, "audiobook.wav")
    return FileResponse(str(wav_path), media_type="audio/wav", filename="audiobook.wav")


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    """Return which stages have been completed for a given job."""
    job_dir = OUT_DIR / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return {
        "job_id": job_id,
        "stages": {
            "extract": (job_dir / "extracted.txt").exists(),
            "refine": (job_dir / "refined.txt").exists(),
            "tts": (job_dir / "audiobook.wav").exists(),
        },
    }


# ---------------------------------------------------------------------------
# Health / dependency checks
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Check that all required models and services are installed."""
    # Check Kokoro model files
    kokoro_model_ok = KOKORO_MODEL.exists()
    voices_ok = VOICES_BIN.exists()
    kokoro_ok = kokoro_model_ok and voices_ok

    # Check Ollama + model availability
    ollama_ok = False
    ollama_detail = ""
    try:
        loop = asyncio.get_event_loop()
        models_response = await loop.run_in_executor(None, ollama.list)
        model_names = [m.model for m in models_response.models]
        ollama_ok = any(LLM_MODEL in name for name in model_names)
        if ollama_ok:
            ollama_detail = f"Model '{LLM_MODEL}' found"
        else:
            ollama_detail = (
                f"Model '{LLM_MODEL}' not found — run: ollama pull {LLM_MODEL}"
            )
    except Exception as e:
        ollama_detail = f"Ollama not reachable: {e}"

    return {
        "ok": kokoro_ok and ollama_ok,
        "kokoro": {
            "ok": kokoro_ok,
            "files": {
                "kokoro-v1.0.onnx": kokoro_model_ok,
                "voices-v1.0.bin": voices_ok,
            },
        },
        "ollama": {
            "ok": ollama_ok,
            "model": LLM_MODEL,
            "detail": ollama_detail,
        },
    }


@app.post("/download-kokoro")
async def download_kokoro():
    """Download missing Kokoro model files into the models/ directory. Streams SSE progress."""

    async def event_stream():
        needed = [(name, dest, url) for name, dest, url in KOKORO_DOWNLOADS if not dest.exists()]

        if not needed:
            yield _sse({"status": "done", "message": "All Kokoro files already present."})
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
                            pct = min(int(block_num * block_size * 100 / total_size), 100)
                            if pct != last_pct[0]:
                                last_pct[0] = pct
                                q.put({"type": "progress", "file": fname, "percent": pct})

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
                        yield _sse({"status": "downloading", "file": msg["file"], "percent": msg["percent"]})
                    elif msg["type"] == "done":
                        yield _sse({"status": "file_done", "file": msg["file"]})
                        break
                    elif msg["type"] == "error":
                        yield _sse({"status": "error", "message": msg["message"]})
                        return
                except queue.Empty:
                    await asyncio.sleep(0.1)

        yield _sse({"status": "done", "message": "Kokoro models downloaded successfully."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
