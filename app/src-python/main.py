import asyncio
import json
import re
import shutil
import uuid
from pathlib import Path

import numpy as np
import ollama
import soundfile as sf
from docling.document_converter import DocumentConverter
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
        converter = DocumentConverter()
        result = await loop.run_in_executor(None, converter.convert, str(pdf_path))
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

        chunk_size = 2000
        chunks = [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)]
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
def tts(job_id: str):
    """
    Generate an audiobook WAV from the refined text using Kokoro TTS.
    Requires stage 2 to have been run first.
    """
    job_dir = _get_job_dir(job_id)
    in_path = job_dir / "refined.txt"
    _require_file(in_path, "refined.txt")

    text = in_path.read_text(encoding="utf-8")

    kokoro = Kokoro(str(KOKORO_MODEL), str(VOICES_BIN))
    chunks = _split_text_smart(text)
    all_samples = []
    sample_rate = None

    for chunk in chunks:
        if not chunk.strip():
            continue
        if not chunk.endswith((".", "!", "?", ";", ":")):
            chunk += "."
        samples, sample_rate = kokoro.create(chunk, voice=VOICE_NAME, speed=1.0)
        all_samples.append(samples)

    out_path = job_dir / "audiobook.wav"
    sf.write(str(out_path), np.concatenate(all_samples), sample_rate)

    return {
        "job_id": job_id,
        "stage": "tts",
        "output_file": str(out_path),
    }


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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
