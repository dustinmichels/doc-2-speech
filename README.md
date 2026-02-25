# Doc 2 Speech

```sh
cd app && bun tauri dev
```

```sh
uv run uvicorn backend.main:app --reload
```

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
