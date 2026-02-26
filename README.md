# Doc 2 Speech

```sh
cd app && bun tauri dev
```

```sh
uv run uvicorn backend.main:app --reload
```

## Testing

```sh
uv run python app/src-python/main.py

# Stage 1 — Extract
curl -X POST http://localhost:8000/jobs/test1/extract \
    -F "pdf=@/Users/dustinmichels/GitRepos/pdf-to-speech/sample-pdfs/just_sustainabilities_pg1.pdf"

# Stage 2 — Refine
curl -X POST http://localhost:8000/jobs/test1/refine

# Stage 3 — TTS
curl -X POST http://localhost:8000/jobs/test1/tts
```

## More

```sh
cd app
bun install
bun run tauri android init
bun run tauri ios init

# For Desktop development, run:
bun run tauri dev

# For Android development, run:
bun run tauri android dev

# For iOS development, run:
bun run tauri ios dev
```

## Install Kokoro TTS

```sh
# Download voice data (bin format is preferred)
wget https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin

# Download the model
wget https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx
```
