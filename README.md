# pdf to audio

Download voice model:

```sh
# Download the model into the models/ folder
curl -L --create-dirs -o models/kokoro-v1.0.onnx https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v1.0.onnx

# Download the voices into the same models/ folder
curl -L -o models/voices-v1.0.bin https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices-v1.0.bin
```

New

```sh
curl -L -o models/kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx

curl -L -o models/voices-v1.0.bin https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```
