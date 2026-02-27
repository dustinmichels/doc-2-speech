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
  <main class="max-w-[480px] mx-auto pt-[10vh] px-8 pb-8 flex flex-col gap-6">
    <h2 class="text-[1.4rem] font-semibold m-0">Converting</h2>
    <p class="text-[0.9em] text-gray-500 m-0 break-all">{{ file.name }}</p>

    <div class="flex flex-col gap-[0.6rem]">
      <div v-for="stage in stages" :key="stage.label" class="flex items-center gap-3">
        <span class="w-[1.4em] flex items-center justify-center shrink-0">
          <span v-if="stage.status === 'idle'" class="icon-idle">○</span>
          <span v-else-if="stage.status === 'loading'" class="spinner"></span>
          <span v-else-if="stage.status === 'done'" class="icon-done">✓</span>
          <span v-else-if="stage.status === 'error'" class="icon-error">✗</span>
        </span>
        <span class="text-[0.95em]">
          {{ stage.label }}
          <span v-if="stage.detail && stage.status === 'loading'" class="text-[0.85em] text-gray-400">
            — {{ stage.detail }}
          </span>
        </span>
      </div>
    </div>

    <p v-if="cancelled" class="text-gray-400 text-[0.9em] m-0">Conversion cancelled.</p>
    <p v-if="errorMsg" class="text-red-500 text-[0.9em] m-0">{{ errorMsg }}</p>

    <div v-if="outputPath" class="flex flex-col gap-3">
      <p class="text-[0.9em] break-all m-0">
        Output: <code class="font-mono bg-black/[0.07] px-[0.3em] py-[0.1em] rounded">{{ outputPath }}</code>
      </p>
      <div class="flex gap-3">
        <button
          class="px-[1.2em] py-[0.6em] rounded-lg border border-transparent bg-white dark:bg-[#0f0f0f98] dark:text-white shadow-sm cursor-pointer text-[0.95em] font-medium transition-[border-color] duration-[0.25s] hover:border-primary"
          @click="togglePlay"
        >
          {{ isPlaying ? "⏸ Pause" : "▶ Play" }}
        </button>
        <button
          class="px-[1.2em] py-[0.6em] rounded-lg border border-transparent bg-white dark:bg-[#0f0f0f98] dark:text-white shadow-sm cursor-pointer text-[0.95em] font-medium transition-[border-color] duration-[0.25s] hover:border-primary"
          @click="openInFinder"
        >Open in Finder</button>
      </div>
      <audio
        ref="audioEl"
        :src="`${BASE}/jobs/${jobId}/audio`"
        @play="isPlaying = true"
        @pause="isPlaying = false"
        @ended="isPlaying = false"
      ></audio>
    </div>

    <div class="flex items-center gap-3 mt-2">
      <button
        v-if="isConverting"
        class="px-[1.4em] py-[0.7em] rounded-lg border border-red-500 bg-transparent text-red-500 text-[1em] font-semibold cursor-pointer transition-colors duration-200 hover:bg-red-500 hover:text-white"
        @click="cancel"
      >
        Cancel
      </button>
      <button
        v-if="!isConverting"
        class="px-[1em] py-[0.5em] rounded-lg border border-gray-300 bg-transparent text-inherit text-[0.9em] cursor-pointer transition-colors duration-200 hover:border-primary hover:text-primary"
        @click="emit('back')"
      >
        ← Convert another file
      </button>
    </div>
  </main>
</template>
