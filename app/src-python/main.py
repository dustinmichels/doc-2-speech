import os
import re
import shutil
import uuid
from pathlib import Path

import numpy as np
import ollama
import soundfile as sf
from docling.document_converter import DocumentConverter
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from kokoro_onnx import Kokoro

LLM_MODEL = "llama3.2:3b"
VOICE_NAME = "af_sky"

PROJECT_ROOT = Path(__file__).parent.parent
KOKORO_MODEL = PROJECT_ROOT / "models" / "kokoro-v1.0.onnx"
VOICES_BIN = PROJECT_ROOT / "models" / "voices-v1.0.bin"
OUT_DIR = PROJECT_ROOT / "out"

app = FastAPI(title="PDF-to-Speech API")


def _get_job_dir(job_id: str) -> Path:
    d = OUT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _require_file(path: Path, label: str):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} not found at {path}. Run the previous stage first.")


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

@app.post("/jobs/{job_id}/extract")
async def extract(job_id: str, pdf: UploadFile = File(...)):
    """
    Upload a PDF and extract its text with Docling.
    Returns the extracted text and its output path.
    """
    job_dir = _get_job_dir(job_id)

    # Save uploaded PDF to job dir
    pdf_path = job_dir / pdf.filename
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(pdf.file, f)

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    text = result.document.export_to_markdown()

    out_path = job_dir / "extracted.txt"
    out_path.write_text(text, encoding="utf-8")

    return {
        "job_id": job_id,
        "stage": "extract",
        "output_file": str(out_path),
        "char_count": len(text),
    }


@app.post("/jobs/extract")
async def extract_new_job(pdf: UploadFile = File(...)):
    """
    Convenience endpoint: creates a new job ID automatically, then runs extraction.
    Returns the job_id for use in subsequent stages.
    """
    job_id = str(uuid.uuid4())
    return await extract(job_id, pdf)


# ---------------------------------------------------------------------------
# Stage 2 — Refine
# ---------------------------------------------------------------------------

@app.post("/jobs/{job_id}/refine")
def refine(job_id: str):
    """
    Clean the extracted text with Ollama LLM (removes citations, page numbers, etc.).
    Requires stage 1 to have been run first.
    """
    job_dir = _get_job_dir(job_id)
    in_path = job_dir / "extracted.txt"
    _require_file(in_path, "extracted.txt")

    raw = in_path.read_text(encoding="utf-8")

    chunk_size = 2000
    cleaned_chunks = []
    for i in range(0, len(raw), chunk_size):
        chunk = raw[i : i + chunk_size]
        try:
            response = ollama.chat(
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
                    {"role": "user", "content": f"Clean this for TTS: \n\n{chunk}"},
                ],
            )
            cleaned_chunks.append(response["message"]["content"])
        except Exception:
            cleaned_chunks.append(chunk)

    refined = " ".join(cleaned_chunks)
    out_path = job_dir / "refined.txt"
    out_path.write_text(refined, encoding="utf-8")

    return {
        "job_id": job_id,
        "stage": "refine",
        "output_file": str(out_path),
        "char_count": len(refined),
    }


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
