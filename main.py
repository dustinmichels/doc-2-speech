import argparse
import os
import sys

import ollama
import soundfile as sf
from kokoro_onnx import Kokoro
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from pydub import AudioSegment

# --- CONFIGURATION (Default Values) ---
LLM_MODEL = "llama3"
VOICE_NAME = "af_sky"
KOKORO_MODEL = "models/kokoro-v1.0.onnx"
VOICES_BIN = "models/voices-v1.0.bin"


def extract_pdf(path):
    print(f"Stage 1: Extracting text from {path} with Marker...")
    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(path)
    text, _, _ = text_from_rendered(rendered)
    return text


def clean_text_with_llm(raw_text):
    print("Stage 2: Cleaning text with Ollama...")
    chunk_size = 2000
    cleaned_chunks = []

    for i in range(0, len(raw_text), chunk_size):
        chunk = raw_text[i : i + chunk_size]
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional editor. Remove citations, page numbers, and image captions. Join words split by hyphens. Do not change the story content.",
                },
                {"role": "user", "content": f"Clean this for TTS: \n\n{chunk}"},
            ],
        )
        cleaned_chunks.append(response["message"]["content"])

    return " ".join(cleaned_chunks)


def generate_tts(text, output_file):
    print("Stage 3: Generating audio with Kokoro...")
    kokoro = Kokoro(KOKORO_MODEL, VOICES_BIN)
    sentences = text.split(". ")
    combined_audio = AudioSegment.empty()

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        samples, sample_rate = kokoro.create(
            sentence + ".", voice=VOICE_NAME, speed=1.0
        )

        temp_chunk = f"temp_{i}.wav"
        sf.write(temp_chunk, samples, sample_rate)
        combined_audio += AudioSegment.from_wav(temp_chunk)
        os.remove(temp_chunk)

    combined_audio.export(output_file, format="wav")
    print(f"Success! Audio saved to {output_file}")


if __name__ == "__main__":
    # Initialize Argument Parser
    parser = argparse.ArgumentParser(
        description="Convert a PDF to an audiobook using Marker, Ollama, and Kokoro."
    )

    # Add Arguments
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument(
        "-o",
        "--output",
        default="output_audiobook.wav",
        help="Output audio filename (default: output_audiobook.wav)",
    )

    args = parser.parse_args()

    # Check if the file exists
    if not os.path.exists(args.pdf_path):
        print(f"Error: The file '{args.pdf_path}' does not exist.")
        sys.exit(1)

    # Execute
    raw_content = extract_pdf(args.pdf_path)

    # Save raw content
    os.makedirs("out", exist_ok=True)
    with open("out/raw_content.txt", "w", encoding="utf-8") as f:
        f.write(raw_content)
    
    # clean_content = clean_text_with_llm(raw_content)
    # generate_tts(clean_content, args.output)
