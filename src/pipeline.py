import os
import re

import numpy as np
import ollama
import soundfile as sf
from docling.document_converter import DocumentConverter
from kokoro_onnx import Kokoro

LLM_MODEL = "llama3.2:3b"
VOICE_NAME = "af_sky"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOKORO_MODEL = os.path.join(PROJECT_ROOT, "models", "kokoro-v1.0.onnx")
VOICES_BIN = os.path.join(PROJECT_ROOT, "models", "voices-v1.0.bin")


def extract_pdf(pdf_path: str, output_dir: str) -> str:
    """Stage 1: Extract text from PDF using Docling. Returns path to extracted.txt."""
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    text = result.document.export_to_markdown()
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "extracted.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    return out_path


def refine_text(output_dir: str) -> str:
    """Stage 2: Clean extracted text with Ollama LLM. Returns path to refined.txt."""
    in_path = os.path.join(output_dir, "extracted.txt")
    with open(in_path, "r", encoding="utf-8") as f:
        raw = f.read()

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
                        "content": "You are a professional editor. Remove citations, page numbers, and image captions. Join words split by hyphens. Do not change the content. Retain headers. Do not add any text.",
                    },
                    {"role": "user", "content": f"Clean this for TTS: \n\n{chunk}"},
                ],
            )
            cleaned_chunks.append(response["message"]["content"])
        except Exception:
            cleaned_chunks.append(chunk)

    refined = " ".join(cleaned_chunks)
    out_path = os.path.join(output_dir, "refined.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(refined)
    return out_path


def text_to_speech(output_dir: str) -> str:
    """Stage 3: Generate audiobook WAV using Kokoro TTS. Returns path to audiobook.wav."""
    in_path = os.path.join(output_dir, "refined.txt")
    with open(in_path, "r", encoding="utf-8") as f:
        text = f.read()

    kokoro = Kokoro(KOKORO_MODEL, VOICES_BIN)
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

    out_path = os.path.join(output_dir, "audiobook.wav")
    sf.write(out_path, np.concatenate(all_samples), sample_rate)
    return out_path


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
