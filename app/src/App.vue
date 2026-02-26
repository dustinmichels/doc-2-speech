<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { revealItemInDir } from "@tauri-apps/plugin-opener";

const BASE = "http://localhost:8000";

type CheckStatus = "pending" | "ok" | "error";

const health = reactive({
  loading: true,
  ollama: { status: "pending" as CheckStatus, detail: "" },
  kokoro: { status: "pending" as CheckStatus, detail: "" },
});

const kokoroFiles = reactive<Record<string, boolean>>({
  "kokoro-v1.0.onnx": false,
  "voices-v1.0.bin": false,
});

const kokoroFileList = computed(() => [
  { name: "kokoro-v1.0.onnx", ok: kokoroFiles["kokoro-v1.0.onnx"] },
  { name: "voices-v1.0.bin", ok: kokoroFiles["voices-v1.0.bin"] },
]);

const allRequirementsOk = computed(
  () =>
    !health.loading &&
    health.ollama.status === "ok" &&
    health.kokoro.status === "ok"
);

const requirementsExpanded = ref(true);

watch(allRequirementsOk, (ok) => {
  if (ok) requirementsExpanded.value = false;
});

function toggleRequirements() {
  requirementsExpanded.value = !requirementsExpanded.value;
}

const kokoroCurrentFile = ref("");
const kokoroCurrentPercent = ref(0);

async function checkHealth() {
  health.loading = true;
  try {
    const res = await fetch(`${BASE}/health`);
    const data = await res.json();
    health.ollama.status = data.ollama.ok ? "ok" : "error";
    health.ollama.detail = data.ollama.detail;
    health.kokoro.status = data.kokoro.ok ? "ok" : "error";
    health.kokoro.detail = "";
    if (data.kokoro.files) {
      kokoroFiles["kokoro-v1.0.onnx"] = !!data.kokoro.files["kokoro-v1.0.onnx"];
      kokoroFiles["voices-v1.0.bin"] = !!data.kokoro.files["voices-v1.0.bin"];
    }
  } catch {
    health.ollama.status = "error";
    health.ollama.detail = "Cannot reach backend server";
    health.kokoro.status = "error";
    health.kokoro.detail = "";
  } finally {
    health.loading = false;
  }
}

async function waitAndCheck() {
  const maxAttempts = 30;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await fetch(`${BASE}/health`);
      break; // server is up
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  await checkHealth();
}

onMounted(waitAndCheck);

const downloadingKokoro = ref(false);

async function downloadKokoro() {
  downloadingKokoro.value = true;
  kokoroCurrentFile.value = "";
  kokoroCurrentPercent.value = 0;
  let downloadError: string | null = null;

  try {
    const res = await fetch(`${BASE}/download-kokoro`, { method: "POST" });
    if (!res.ok) throw new Error(`Download failed: ${res.statusText}`);
    await consumeSSE(res, (event) => {
      if (event.status === "downloading") {
        kokoroCurrentFile.value = event.file ?? "";
        kokoroCurrentPercent.value = event.percent ?? 0;
      } else if (event.status === "file_done") {
        kokoroFiles[event.file] = true;
        kokoroCurrentFile.value = "";
        kokoroCurrentPercent.value = 0;
      } else if (event.status === "error") {
        downloadError = event.message ?? "Download failed";
      }
    });
    if (downloadError) throw new Error(downloadError);
  } catch (err: any) {
    health.kokoro.detail = err.message ?? "Download failed";
  } finally {
    downloadingKokoro.value = false;
    kokoroCurrentFile.value = "";
    await checkHealth();
  }
}

const selectedFile = ref<File | null>(null);
const jobId = ref<string | null>(null);
const isConverting = ref(false);
const abortController = ref<AbortController | null>(null);
const outputPath = ref<string | null>(null);
const errorMsg = ref<string | null>(null);
const isPlaying = ref(false);
const audioEl = ref<HTMLAudioElement | null>(null);

type StageStatus = "idle" | "loading" | "done" | "error";

const stages = reactive([
  { label: "Extract text", status: "idle" as StageStatus, detail: "" },
  { label: "Refine text", status: "idle" as StageStatus, detail: "" },
  { label: "Generate audio", status: "idle" as StageStatus, detail: "" },
]);

/** Read a POST SSE stream, calling onEvent for each parsed event. Returns the last event. */
async function consumeSSE(response: Response, onEvent: (data: any) => void): Promise<any> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastData: any = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        onEvent(data);
        lastData = data;
      }
    }
  }
  return lastData;
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  outputPath.value = null;
  errorMsg.value = null;
  isPlaying.value = false;
  stages.forEach((s) => { s.status = "idle"; s.detail = ""; });
}

function togglePlay() {
  if (!audioEl.value) return;
  if (isPlaying.value) {
    audioEl.value.pause();
  } else {
    audioEl.value.play();
  }
}

function openInFinder() {
  if (outputPath.value) revealItemInDir(outputPath.value);
}

function cancel() {
  abortController.value?.abort();
}

async function convert() {
  if (!selectedFile.value) return;

  abortController.value = new AbortController();
  const signal = abortController.value.signal;

  isConverting.value = true;
  outputPath.value = null;
  errorMsg.value = null;
  stages.forEach((s) => { s.status = "idle"; s.detail = ""; });

  try {
    // Stage 1: Extract
    stages[0].status = "loading";
    const form = new FormData();
    form.append("pdf", selectedFile.value);
    const res1 = await fetch(`${BASE}/jobs/extract`, { method: "POST", body: form, signal });
    if (!res1.ok) throw new Error(`Extract failed: ${res1.statusText}`);
    const data1 = await consumeSSE(res1, (event) => {
      stages[0].detail = event.message ?? "";
    });
    jobId.value = data1.job_id;
    stages[0].status = "done";
    stages[0].detail = "";

    // Stage 2: Refine
    stages[1].status = "loading";
    const res2 = await fetch(`${BASE}/jobs/${jobId.value}/refine`, { method: "POST", signal });
    if (!res2.ok) throw new Error(`Refine failed: ${res2.statusText}`);
    await consumeSSE(res2, (event) => {
      if (event.total && event.completed != null) {
        stages[1].detail = `${Math.round((event.completed / event.total) * 100)}%`;
      } else {
        stages[1].detail = event.message ?? "";
      }
    });
    stages[1].status = "done";
    stages[1].detail = "";

    // Stage 3: TTS
    stages[2].status = "loading";
    const res3 = await fetch(`${BASE}/jobs/${jobId.value}/tts`, { method: "POST", signal });
    if (!res3.ok) throw new Error(`TTS failed: ${res3.statusText}`);
    const data3 = await consumeSSE(res3, (event) => {
      if (event.status === "error") throw new Error(event.message ?? "TTS error");
      if (event.total && event.completed != null) {
        stages[2].detail = `${Math.round((event.completed / event.total) * 100)}%`;
      } else {
        stages[2].detail = event.message ?? "";
      }
    });
    if (data3?.status === "error") throw new Error(data3.message ?? "TTS error");
    stages[2].status = "done";
    stages[2].detail = "";
    outputPath.value = data3?.output_file;
  } catch (err: any) {
    if (err.name === "AbortError") {
      stages.forEach((s) => { if (s.status === "loading") s.status = "idle"; });
    } else {
      const failedIndex = stages.findIndex((s) => s.status === "loading");
      if (failedIndex !== -1) stages[failedIndex].status = "error";
      errorMsg.value = err.message ?? "An unknown error occurred.";
    }
  } finally {
    isConverting.value = false;
    abortController.value = null;
  }
}
</script>

<template>
  <main class="container">
    <h1>PDF to Speech</h1>

    <div class="health-section">
      <div class="health-header" @click="toggleRequirements">
        <div class="health-header-left">
          <span class="health-toggle-arrow" :class="{ expanded: requirementsExpanded }">▶</span>
          <span class="health-title">Requirements</span>
          <span v-if="!requirementsExpanded" class="health-icon">
            <span v-if="health.loading" class="spinner"></span>
            <span v-else-if="allRequirementsOk" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
        </div>
        <button class="recheck-btn" :disabled="health.loading" @click.stop="checkHealth">
          {{ health.loading ? "Checking…" : "Re-check" }}
        </button>
      </div>
      <template v-if="requirementsExpanded">
        <div class="health-row">
          <span class="health-icon">
            <span v-if="health.loading" class="spinner"></span>
            <span v-else-if="health.ollama.status === 'ok'" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
          <span class="health-label">
            Ollama model
            <span class="health-detail">{{ health.ollama.detail }}</span>
          </span>
        </div>
        <div class="health-row">
          <span class="health-icon">
            <span v-if="health.loading || downloadingKokoro" class="spinner"></span>
            <span v-else-if="health.kokoro.status === 'ok'" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
          <span class="health-label">Kokoro TTS models</span>
          <button
            v-if="health.kokoro.status === 'error' && !downloadingKokoro && !health.loading"
            class="download-btn"
            @click="downloadKokoro"
          >
            Download
          </button>
        </div>
        <div v-if="health.kokoro.status === 'error' || downloadingKokoro" class="health-sublist">
          <div v-for="file in kokoroFileList" :key="file.name" class="health-subrow">
            <span class="health-icon">
              <span v-if="file.ok" class="icon-done">✓</span>
              <span v-else class="icon-error">✗</span>
            </span>
            <span class="health-sublabel">
              {{ file.name }}
              <span v-if="downloadingKokoro && kokoroCurrentFile === file.name" class="health-detail">
                {{ kokoroCurrentPercent }}%
              </span>
            </span>
          </div>
        </div>
      </template>
    </div>

    <div class="file-section">
      <label class="file-btn">
        Select Document
        <input type="file" accept=".pdf" @change="onFileChange" hidden />
      </label>
      <span v-if="selectedFile" class="filename">{{ selectedFile.name }}</span>
    </div>

    <div class="convert-row">
      <button
        class="convert-btn"
        :disabled="!selectedFile || isConverting || health.ollama.status !== 'ok' || health.kokoro.status !== 'ok'"
        @click="convert"
      >
        Convert to Speech
      </button>
      <button v-if="isConverting" class="cancel-btn" @click="cancel">
        Cancel
      </button>
    </div>

    <div v-if="stages.some((s) => s.status !== 'idle')" class="stages">
      <div v-for="stage in stages" :key="stage.label" class="stage-row">
        <span class="stage-icon">
          <span v-if="stage.status === 'idle'" class="icon-idle">○</span>
          <span v-else-if="stage.status === 'loading'" class="spinner"></span>
          <span v-else-if="stage.status === 'done'" class="icon-done">✓</span>
          <span v-else-if="stage.status === 'error'" class="icon-error">✗</span>
        </span>
        <span class="stage-label">
          {{ stage.label }}
          <span v-if="stage.detail && stage.status === 'loading'" class="stage-detail">
            — {{ stage.detail }}
          </span>
        </span>
      </div>
    </div>

    <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

    <div v-if="outputPath" class="output-section">
      <p class="output-path">Output: <code>{{ outputPath }}</code></p>
      <div class="output-actions">
        <button class="action-btn" @click="togglePlay">
          {{ isPlaying ? "⏸ Pause" : "▶ Play" }}
        </button>
        <button class="action-btn" @click="openInFinder">Open in Finder</button>
      </div>
      <audio
        ref="audioEl"
        :src="`${BASE}/jobs/${jobId}/audio`"
        @play="isPlaying = true"
        @pause="isPlaying = false"
        @ended="isPlaying = false"
      ></audio>
    </div>
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

.convert-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
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
}

.cancel-btn {
  padding: 0.7em 1.4em;
  border-radius: 8px;
  border: 1px solid #ef4444;
  background: transparent;
  color: #ef4444;
  font-size: 1em;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.cancel-btn:hover {
  background: #ef4444;
  color: #fff;
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

.stage-detail {
  font-size: 0.85em;
  color: #888;
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

.output-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.output-path {
  font-size: 0.9em;
  word-break: break-all;
  margin: 0;
}

.output-path code {
  font-family: monospace;
  background: rgba(0, 0, 0, 0.07);
  padding: 0.1em 0.3em;
  border-radius: 4px;
}

.output-actions {
  display: flex;
  gap: 0.75rem;
}

.action-btn {
  padding: 0.6em 1.2em;
  border-radius: 8px;
  border: 1px solid transparent;
  background-color: #ffffff;
  box-shadow: 0 2px 2px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  font-size: 0.95em;
  font-weight: 500;
  transition: border-color 0.25s;
}

.action-btn:hover {
  border-color: #396cd8;
}

@media (prefers-color-scheme: dark) {
  .action-btn {
    color: #ffffff;
    background-color: #0f0f0f98;
  }
}

.health-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.85rem 1rem;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.04);
}

@media (prefers-color-scheme: dark) {
  .health-section {
    background: rgba(255, 255, 255, 0.06);
  }
}

.health-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.25rem;
  cursor: pointer;
  user-select: none;
}

.health-header-left {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.health-toggle-arrow {
  font-size: 0.65em;
  color: #888;
  display: inline-block;
  transition: transform 0.2s ease;
  line-height: 1;
}

.health-toggle-arrow.expanded {
  transform: rotate(90deg);
}

.health-title {
  font-size: 0.8em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #888;
}

.recheck-btn {
  font-size: 0.78em;
  padding: 0.2em 0.6em;
  border-radius: 4px;
  border: 1px solid #ccc;
  background: transparent;
  cursor: pointer;
  color: inherit;
}

.recheck-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.health-row {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
}

.health-icon {
  width: 1.2em;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.health-label {
  font-size: 0.9em;
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: baseline;
}

.health-detail {
  font-size: 0.85em;
  color: #888;
}

.health-sublist {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding-left: 1.8rem;
}

.health-subrow {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.health-sublabel {
  font-size: 0.85em;
  color: #555;
  display: flex;
  gap: 0.3rem;
  align-items: baseline;
}

@media (prefers-color-scheme: dark) {
  .health-sublabel {
    color: #aaa;
  }
}

.download-btn {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 0.78em;
  padding: 0.2em 0.7em;
  border-radius: 4px;
  border: 1px solid #396cd8;
  background: transparent;
  color: #396cd8;
  cursor: pointer;
  white-space: nowrap;
}

.download-btn:hover {
  background: #396cd8;
  color: #fff;
}
</style>
