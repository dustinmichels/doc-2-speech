#!/bin/zsh
set -e  # Exit on error

PDF_PATH="$1"

if [ -z "$PDF_PATH" ]; then
  echo "Usage: ./run.zsh <path-to-pdf>"
  exit 1
fi

echo "--- Running Stage 1: Text Extraction ---"
uv run 1-extract-text.py "$PDF_PATH"

echo "--- Running Stage 2: Refining Text ---"
uv run 2-refine-text.py "$PDF_PATH"

echo "--- Running Stage 3: Text to Speech ---"
uv run 3-text-to-speech.py "$PDF_PATH"

echo "--- All stages completed successfully ---"
