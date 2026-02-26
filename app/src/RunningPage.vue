<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { revealItemInDir } from "@tauri-apps/plugin-opener";
import { BASE, consumeSSE } from "./utils";

const props = defineProps<{
  file: File;
  outBaseDir: string;
  outName: string;
}>();

const emit = defineEmits<{ back: [] }>();

type StageStatus = "idle" | "loading" | "done" | "error";

const stages = reactive([
  { label: "Extract text", status: "idle" as StageStatus, detail: "" },
  { label: "Refine text", status: "idle" as StageStatus, detail: "" },
  { label: "Generate audio", status: "idle" as StageStatus, detail: "" },
]);

const jobId = ref<string | null>(null);
const isConverting = ref(false);
const cancelled = ref(false);
const abortController = ref<AbortController | null>(null);
const outputPath = ref<string | null>(null);
const errorMsg = ref<string | null>(null);
const isPlaying = ref(false);
const audioEl = ref<HTMLAudioElement | null>(null);

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

async function run() {
  abortController.value = new AbortController();
  const signal = abortController.value.signal;

  isConverting.value = true;
  cancelled.value = false;

  try {
    // Stage 1: Extract
    stages[0].status = "loading";
    const form = new FormData();
    form.append("pdf", props.file);
    const resolvedOutDir = `${props.outBaseDir}/${props.outName}`;
    form.append("out_dir", resolvedOutDir);
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
      cancelled.value = true;
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

onMounted(run);
</script>

<template>
  <main class="container">
    <h2>Converting</h2>
    <p class="converting-filename">{{ file.name }}</p>

    <div class="stages">
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

    <p v-if="cancelled" class="cancelled-msg">Conversion cancelled.</p>
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

    <div class="bottom-actions">
      <button v-if="isConverting" class="cancel-btn" @click="cancel">
        Cancel
      </button>
      <button v-if="!isConverting" class="back-btn" @click="emit('back')">
        ← Convert another file
      </button>
    </div>
  </main>
</template>

<style scoped>
.converting-filename {
  font-size: 0.9em;
  color: #666;
  margin: 0;
  word-break: break-all;
}

h2 {
  font-size: 1.4rem;
  font-weight: 600;
  margin: 0;
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

.stage-label {
  font-size: 0.95em;
}

.stage-detail {
  font-size: 0.85em;
  color: #888;
}

.cancelled-msg {
  color: #888;
  font-size: 0.9em;
  margin: 0;
}

.error-msg {
  color: #ef4444;
  font-size: 0.9em;
  margin: 0;
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

.bottom-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
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

.back-btn {
  padding: 0.5em 1em;
  border-radius: 8px;
  border: 1px solid #ccc;
  background: transparent;
  color: inherit;
  font-size: 0.9em;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.back-btn:hover {
  border-color: #396cd8;
  color: #396cd8;
}
</style>
