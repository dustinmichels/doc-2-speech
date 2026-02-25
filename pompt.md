# prompt

Inside app, I want to replace my boilerplate tauri app with one that converts a PDF to speech.

The backend will use python and the fastapi framework.

I have the the FASTAPI backend in: `app/src-python/main.py`

I want to modify `tauri.conf.json` to run this backend. Something like:

```json
"build": {
  "beforeDevCommand": "cd .. && uv run python src-python/main.py",
  "devPath": "http://localhost:3000",
  "distDir": "../dist"
}
```

The app UI should be as follows:

- A file picker. It says "select document"
- A button that says "Convert to Speech"
- Status indicators for each stage of the conversion. Each should have a loading icon that turns into a green checkmark when done.
  1. "Extracting text..."
  2. "Refining text..."
  3. "Generating audio..."

When the conversion is done, just save it to an "out" directory and show the path to the output file.
