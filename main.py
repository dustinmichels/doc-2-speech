import os

import ollama
import soundfile as sf
from kokoro_onnx import Kokoro
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from pydub import AudioSegment

# --- CONFIGURATION ---
PDF_PATH = "your_book.pdf"
OUTPUT_AUDIO = "output_audiobook.wav"
LLM_MODEL = "llama3"
VOICE_NAME = "af_sky"  # Options: af_bella, af_sarah, am_adam, etc.
KOKORO_MODEL = "kokoro-v0_19.onnx"
VOICES_BIN = "voices.bin"


def extract_pdf(path):
    print("Stage 1: Extracting text with Marker...")
    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(path)
    text, _, _ = text_from_rendered(rendered)
    return text


def clean_text_with_llm(raw_text):
    print("Stage 2: Cleaning text with Ollama...")
    # We process in chunks to stay within LLM context limits
    chunk_size = 2000
    cleaned_chunks = []

    for i in range(0, len(raw_text), chunk_size):
        chunk = raw_text[i : i + chunk_size]
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional editor. Remove citations, page numbers, and image captions from the text. Join words split by hyphens. Do not change the story content.",
                },
                {"role": "user", "content": f"Clean this for TTS: \n\n{chunk}"},
            ],
        )
        cleaned_chunks.append(response["message"]["content"])

    return " ".join(cleaned_chunks)


def generate_tts(text, output_file):
    print("Stage 3: Generating audio with Kokoro...")
    kokoro = Kokoro(KOKORO_MODEL, VOICES_BIN)

    # Split text into sentences or small paragraphs for better processing
    sentences = text.split(". ")
    combined_audio = AudioSegment.empty()

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        # Generate raw audio data
        samples, sample_rate = kokoro.create(
            sentence + ".", voice=VOICE_NAME, speed=1.0
        )

        # Save temporary chunk and append to main file
        temp_chunk = f"temp_{i}.wav"
        sf.write(temp_chunk, samples, sample_rate)
        combined_audio += AudioSegment.from_wav(temp_chunk)
        os.remove(temp_chunk)

    combined_audio.export(output_file, format="wav")
    print(f"Success! Audio saved to {output_file}")


if __name__ == "__main__":
    raw_content = extract_pdf(PDF_PATH)
    clean_content = clean_text_with_llm(raw_content)
    generate_tts(clean_content, OUTPUT_AUDIO)
