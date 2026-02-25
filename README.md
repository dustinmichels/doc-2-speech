# pdf-to-speech

Convert a PDF into a spoken audio file using a three-stage pipeline:

1. **Extract** — Pull text from the PDF using [Docling](https://github.com/DS4SD/docling)
2. **Refine** — Clean the text for TTS using a local LLM via [Ollama](https://ollama.com/) (removes citations, page numbers, image captions, etc.)
3. **Synthesize** — Generate audio using [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (local, offline TTS)

Output is saved to `out/<pdf-name>/audiobook.wav`.

## Requirements

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) for package management
- [Ollama](https://ollama.com/) running locally with the `llama3.2:3b` model
- Kokoro model files (see below)

## Setup

### 1. Install dependencies

```sh
uv sync
```

### 2. Download the Kokoro model files

```sh
curl -L --create-dirs -o models/kokoro-v1.0.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx

curl -L -o models/voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

### 3. Pull the Ollama model

```sh
ollama pull llama3.2:3b
```

## Usage

### Run all stages at once

```sh
./run.zsh path/to/document.pdf
```

### Run stages individually

```sh
# Stage 1: Extract text from PDF → out/<name>/extracted.txt
uv run 1-extract-text.py path/to/document.pdf

# Stage 2: Refine text for TTS → out/<name>/refined.txt
uv run 2-refine-text.py path/to/document.pdf

# Stage 3: Generate audio → out/<name>/audiobook.wav
uv run 3-text-to-speech.py path/to/document.pdf
```

Each script takes the original PDF path as its argument and uses the filename to locate the shared output directory (`out/<pdf-name>/`).

## How it works

| Stage | Script                | Input           | Output          | Tool                 |
| ----- | --------------------- | --------------- | --------------- | -------------------- |
| 1     | `1-extract-text.py`   | PDF file        | `extracted.txt` | Docling              |
| 2     | `2-refine-text.py`    | `extracted.txt` | `refined.txt`   | Ollama (llama3.2:3b) |
| 3     | `3-text-to-speech.py` | `refined.txt`   | `audiobook.wav` | Kokoro ONNX          |

Stage 2 processes the text in 2000-character chunks, sending each to the LLM with instructions to remove noise (citations, page numbers, figure captions) while preserving content and headers. Stage 3 splits the refined text into sentence-level chunks and stitches the audio together into a single WAV file.
