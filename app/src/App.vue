<script setup lang="ts">
import { ref, reactive } from "vue";

const BASE = "http://localhost:8000";

const selectedFile = ref<File | null>(null);
const jobId = ref<string | null>(null);
const isConverting = ref(false);
const outputPath = ref<string | null>(null);
const errorMsg = ref<string | null>(null);

type StageStatus = "idle" | "loading" | "done" | "error";

const stages = reactive([
  { label: "Extracting text...", status: "idle" as StageStatus },
  { label: "Refining text...", status: "idle" as StageStatus },
  { label: "Generating audio...", status: "idle" as StageStatus },
]);

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  outputPath.value = null;
  errorMsg.value = null;
  stages.forEach((s) => (s.status = "idle"));
}

async function convert() {
  if (!selectedFile.value) return;

  isConverting.value = true;
  outputPath.value = null;
  errorMsg.value = null;
  stages.forEach((s) => (s.status = "idle"));

  try {
    // Stage 1: Extract
    stages[0].status = "loading";
    const form = new FormData();
    form.append("pdf", selectedFile.value);
    const res1 = await fetch(`${BASE}/jobs/extract`, { method: "POST", body: form });
    if (!res1.ok) throw new Error(`Extract failed: ${res1.statusText}`);
    const data1 = await res1.json();
    jobId.value = data1.job_id;
    stages[0].status = "done";

    // Stage 2: Refine
    stages[1].status = "loading";
    const res2 = await fetch(`${BASE}/jobs/${jobId.value}/refine`, { method: "POST" });
    if (!res2.ok) throw new Error(`Refine failed: ${res2.statusText}`);
    stages[1].status = "done";

    // Stage 3: TTS
    stages[2].status = "loading";
    const res3 = await fetch(`${BASE}/jobs/${jobId.value}/tts`, { method: "POST" });
    if (!res3.ok) throw new Error(`TTS failed: ${res3.statusText}`);
    const data3 = await res3.json();
    stages[2].status = "done";
    outputPath.value = data3.output_file;
  } catch (err: any) {
    const failedIndex = stages.findIndex((s) => s.status === "loading");
    if (failedIndex !== -1) stages[failedIndex].status = "error";
    errorMsg.value = err.message ?? "An unknown error occurred.";
  } finally {
    isConverting.value = false;
  }
}
</script>

<template>
  <main class="container">
    <h1>PDF to Speech</h1>

    <div class="file-section">
      <label class="file-btn">
        Select Document
        <input type="file" accept=".pdf" @change="onFileChange" hidden />
      </label>
      <span v-if="selectedFile" class="filename">{{ selectedFile.name }}</span>
    </div>

    <button
      class="convert-btn"
      :disabled="!selectedFile || isConverting"
      @click="convert"
    >
      Convert to Speech
    </button>

    <div v-if="stages.some((s) => s.status !== 'idle')" class="stages">
      <div v-for="stage in stages" :key="stage.label" class="stage-row">
        <span class="stage-icon">
          <span v-if="stage.status === 'idle'" class="icon-idle">○</span>
          <span v-else-if="stage.status === 'loading'" class="spinner"></span>
          <span v-else-if="stage.status === 'done'" class="icon-done">✓</span>
          <span v-else-if="stage.status === 'error'" class="icon-error">✗</span>
        </span>
        <span class="stage-label">{{ stage.label }}</span>
      </div>
    </div>

    <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

    <p v-if="outputPath" class="output-path">
      Output saved to: <code>{{ outputPath }}</code>
    </p>
  </main>
</template>

<style>
:root {
  font-family: Inter, Avenir, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 24px;
  font-weight: 400;
  color: #0f0f0f;
  background-color: #f6f6f6;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

@media (prefers-color-scheme: dark) {
  :root {
    color: #f6f6f6;
    background-color: #2f2f2f;
  }
  input,
  button,
  .file-btn {
    color: #ffffff;
    background-color: #0f0f0f98;
  }
}
</style>

<style scoped>
.container {
  max-width: 480px;
  margin: 0 auto;
  padding: 10vh 2rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

h1 {
  font-size: 1.8rem;
  font-weight: 600;
}

.file-section {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.file-btn {
  display: inline-block;
  padding: 0.6em 1.2em;
  border-radius: 8px;
  border: 1px solid transparent;
  background-color: #ffffff;
  box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  font-size: 1em;
  font-weight: 500;
  transition: border-color 0.25s;
}

.file-btn:hover {
  border-color: #396cd8;
}

.filename {
  font-size: 0.9em;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.convert-btn {
  padding: 0.7em 1.4em;
  border-radius: 8px;
  border: 1px solid transparent;
  background-color: #396cd8;
  color: #fff;
  font-size: 1em;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  align-self: flex-start;
}

.convert-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.convert-btn:not(:disabled):hover {
  opacity: 0.85;
}

.stages {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.stage-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.stage-icon {
  width: 1.4em;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-idle {
  color: #999;
}

.icon-done {
  color: #22c55e;
  font-weight: 700;
}

.icon-error {
  color: #ef4444;
  font-weight: 700;
}

.spinner {
  display: inline-block;
  width: 1em;
  height: 1em;
  border: 2px solid #396cd8;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-msg {
  color: #ef4444;
  font-size: 0.9em;
}

.output-path {
  font-size: 0.9em;
  word-break: break-all;
}

.output-path code {
  font-family: monospace;
  background: rgba(0, 0, 0, 0.07);
  padding: 0.1em 0.3em;
  border-radius: 4px;
}
</style>
