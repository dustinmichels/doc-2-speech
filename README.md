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
