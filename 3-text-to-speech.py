import argparse
import os
import sys
import soundfile as sf
from kokoro_onnx import Kokoro
from pydub import AudioSegment

# Configuration
VOICE_NAME = "af_sky"
KOKORO_MODEL = "models/kokoro-v1.0.onnx"
VOICES_BIN = "models/voices-v1.0.bin"

def generate_tts(text, output_file):
    print("Stage 3: Generating audio with Kokoro...")
    
    # Validation
    if not os.path.exists(KOKORO_MODEL):
        print(f"Error: Kokoro model not found at '{KOKORO_MODEL}'")
        sys.exit(1)
    if not os.path.exists(VOICES_BIN):
        print(f"Error: Voices bin not found at '{VOICES_BIN}'")
        sys.exit(1)

    try:
        kokoro = Kokoro(KOKORO_MODEL, VOICES_BIN)
    except Exception as e:
        print(f"Error initializing Kokoro: {e}")
        sys.exit(1)

    sentences = text.split(". ")
    combined_audio = AudioSegment.empty()
    total_sentences = len(sentences)

    print(f"  Processing {total_sentences} sentences...")

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue
        
        # Helper logging
        if (i + 1) % 5 == 0:
            print(f"  Sentence {i + 1}/{total_sentences}...")

        try:
            samples, sample_rate = kokoro.create(
                sentence + ".", voice=VOICE_NAME, speed=1.0
            )

            temp_chunk = f"temp_{i}.wav"
            sf.write(temp_chunk, samples, sample_rate)
            combined_audio += AudioSegment.from_wav(temp_chunk)
            os.remove(temp_chunk)
        except Exception as e:
             print(f"  Warning: Error generating audio for sentence '{sentence[:20]}...': {e}")

    combined_audio.export(output_file, format="wav")
    print(f"Success! Audio saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 3: Convert text to speech")
    parser.add_argument("pdf_path", help="Path to the original PDF file (used to locate output directory)")
    args = parser.parse_args()

    # Locate the output directory
    pdf_name = os.path.splitext(os.path.basename(args.pdf_path))[0]
    output_dir = os.path.join("out", pdf_name)
    input_path = os.path.join(output_dir, "refined.txt")

    if not os.path.exists(output_dir):
        print(f"Error: Directory '{output_dir}' does not exist. Please run steps 1 and 2.")
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"Error: File '{input_path}' not found. Please run step 2 first.")
        sys.exit(1)

    print(f"Reading from {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    output_path = os.path.join(output_dir, "audiobook.wav")
    generate_tts(text, output_path)
