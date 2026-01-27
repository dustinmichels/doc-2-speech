# PDF to Speech Plan

## 1. Extraction: Marker or Nougat

Standard PDF tools extract text based on character position, which is why they often catch page numbers and footers in the middle of a sentence.

- **Marker:** Currently the fastest and most versatile option. It uses a pipeline of models to detect the layout (headers, footers, sidebars) and specifically targets them for removal.
- **How to use:** Install via Python (`pip install marker-pdf`). Run it via command line:
  `marker_single /path/to/file.pdf /output/folder/ --batch_multiplier 2`
- **Why it's better:** It outputs **Markdown**. This means it identifies bold text, lists, and tables, which helps the later steps understand the document's structure.

- **Nougat:** Built by Meta specifically for academic papers. It excels at complex math and nested tables but is significantly slower than Marker.

---

## 2. Cleaning: Local LLM (Ollama)

Even with Marker, some "junk" (like citations: _[12, 14]_) might remain. A local LLM can act as a "smart editor" to sanitize the text before the AI reads it aloud.

- **Setup:** Use **Ollama** to run a model like `Llama-3-8B` or `Mistral`.
- **The Prompt:** You want to be very specific so the LLM doesn't rewrite the story, just cleans the formatting.

  > "I am going to provide text from a PDF. Please remove all citations (e.g., [1], (Smith, 2023)), page numbers, and image captions. Join hyphenated words that were split across lines. Do not change the wording of the actual story/content. Output only the cleaned text."

- **Automation:** You can script this in Python using the `ollama` library to process the Markdown file from Step 1 in 2,000-word chunks.

---

## 3. Synthesis: Kokoro-82M (via kokoro-onnx)

Kokoro is a breakthrough because it provides "human-level" prosody (the rhythm and intonation of speech) in a model small enough to run on a toaster.

- **Why `kokoro-onnx`?** The ONNX version of the model is highly optimized. It allows you to generate audio faster than real-time on a standard CPU—no expensive Nvidia GPU required.
- **Implementation:**

1. **Install:** `pip install kokoro-onnx onnxruntime`
2. **Voice Selection:** You can choose from various "styles" (e.g., `af_bella` for a soft female voice, `am_adam` for a deep male voice).
3. **Python Snippet:**

```python
from kokoro_onnx import Kokoro
kokoro = Kokoro("kokoro-v0_19.onnx", "voices.bin")
samples, sample_rate = kokoro.create("Your cleaned text here", voice="af_sky", speed=1.0)
# Save to file using soundfile or similar
```

---

## Summary of the "Pro" Workflow

| Step           | Tool        | Purpose                                    | Output          |
| -------------- | ----------- | ------------------------------------------ | --------------- |
| **1. Extract** | **Marker**  | Strips layout artifacts (headers/footers). | `.md` file      |
| **2. Clean**   | **Llama 3** | Removes citations, fixes broken words.     | Clean `.txt`    |
| **3. Speak**   | **Kokoro**  | High-fidelity, natural-sounding voice.     | `.wav` / `.mp3` |

### One Final "Pro" Tip

If you are doing this for a long book, **chunk your text**. Don't send 50,000 words to the TTS at once. Break it into chapters, generate the audio files individually, and then use a tool like `ffmpeg` to merge them. This prevents memory issues and makes it easier to re-generate a single chapter if you don't like the tone.

**Would you like a sample Python script that connects these three tools into a single automated pipeline?**
