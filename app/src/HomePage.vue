<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { homeDir, join } from "@tauri-apps/api/path";
import OllamaInstructions from "./OllamaInstructions.vue";
import { BASE, setBase, consumeSSE } from "./utils";

const emit = defineEmits<{ start: [file: File, outBaseDir: string, outName: string] }>();

const showOllamaInstructions = ref(false);

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

const requirementsExpanded = ref(false);

watch(() => health.loading, (loading) => {
  if (!loading) requirementsExpanded.value = !allRequirementsOk.value;
});

function toggleRequirements() {
  requirementsExpanded.value = !requirementsExpanded.value;
}

const kokoroCurrentFile = ref("");
const kokoroCurrentPercent = ref(0);

import { Command } from "@tauri-apps/plugin-shell";

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

let sidecarSpawned = false;

async function waitAndCheck() {
  if (!sidecarSpawned) {
    try {
      const command = Command.sidecar("binaries/main");

      command.stdout.on("data", (line) => {
        const match = line.match(/PORT_ALLOCATED=(\d+)/);
        if (match) {
          const port = match[1];
          setBase(`http://localhost:${port}`);
        }
        console.log(`Sidecar: ${line}`);
      });

      command.stderr.on("data", (line) => {
        console.error(`Sidecar Error: ${line}`);
      });

      await command.spawn();
      sidecarSpawned = true;
    } catch (e) {
      console.error("Failed to spawn sidecar:", e);
    }
  }

  const maxAttempts = 30;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await fetch(`${BASE}/health`);
      break;
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
const outBaseDir = ref<string>("");
const outName = ref<string>("");

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  if (selectedFile.value) {
    outBaseDir.value = await join(await homeDir(), "MakeDocTalk", "docs");
    outName.value = selectedFile.value.name.replace(/\.pdf$/i, "");
  } else {
    outBaseDir.value = "";
    outName.value = "";
  }
}

async function browseFolder() {
  const selected = await openDialog({ directory: true, defaultPath: outBaseDir.value });
  if (selected) outBaseDir.value = selected as string;
}

function startConversion() {
  if (!selectedFile.value) return;
  emit("start", selectedFile.value, outBaseDir.value, outName.value);
}
</script>

<template>
  <OllamaInstructions
    v-if="showOllamaInstructions"
    :ollama-installed="health.ollama.status === 'ok'"
    @back="showOllamaInstructions = false"
    @status-updated="(ok, detail) => { health.ollama.status = ok ? 'ok' : 'error'; health.ollama.detail = detail; }"
  />
  <main v-else class="max-w-[480px] mx-auto pt-[10vh] px-8 pb-8 flex flex-col gap-6">
    <h1 class="text-[1.8rem] font-semibold">PDF to Speech</h1>

    <!-- Requirements / Health Check -->
    <div class="flex flex-col gap-2 py-[0.85rem] px-4 rounded-lg bg-black/[0.04] dark:bg-white/[0.06]">
      <div class="flex items-center justify-between mb-1 cursor-pointer select-none" @click="toggleRequirements">
        <div class="flex items-center gap-[0.4rem]">
          <span
            class="text-[0.65em] text-gray-400 inline-block transition-transform duration-200 leading-none"
            :class="requirementsExpanded ? 'rotate-90' : ''"
          >▶</span>
          <span class="text-[0.8em] font-semibold uppercase tracking-[0.05em] text-gray-400">Requirements</span>
          <span v-if="!requirementsExpanded" class="w-[1.2em] flex items-center justify-center shrink-0">
            <span v-if="health.loading" class="spinner"></span>
            <span v-else-if="allRequirementsOk" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
        </div>
        <button
          class="text-[0.78em] px-[0.6em] py-[0.2em] rounded border border-gray-300 bg-transparent text-inherit cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="health.loading"
          @click.stop="checkHealth"
        >
          {{ health.loading ? "Checking…" : "Re-check" }}
        </button>
      </div>

      <template v-if="requirementsExpanded">
        <div class="flex items-baseline gap-[0.6rem]">
          <span class="w-[1.2em] flex items-center justify-center shrink-0">
            <span v-if="health.loading" class="spinner"></span>
            <span v-else-if="health.ollama.status === 'ok'" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
          <span class="text-[0.9em] flex flex-wrap gap-[0.3rem] items-baseline">
            Ollama model
            <span class="text-[0.85em] text-gray-400">{{ health.ollama.detail }}</span>
          </span>
          <button
            v-if="health.ollama.status === 'error' && !health.loading"
            class="ml-auto shrink-0 text-[0.78em] px-[0.7em] py-[0.2em] rounded border border-primary bg-transparent text-primary cursor-pointer whitespace-nowrap hover:bg-primary hover:text-white transition-colors duration-150"
            @click="showOllamaInstructions = true"
          >
            Install
          </button>
        </div>

        <div class="flex items-baseline gap-[0.6rem]">
          <span class="w-[1.2em] flex items-center justify-center shrink-0">
            <span v-if="health.loading || downloadingKokoro" class="spinner"></span>
            <span v-else-if="health.kokoro.status === 'ok'" class="icon-done">✓</span>
            <span v-else class="icon-error">✗</span>
          </span>
          <span class="text-[0.9em]">Kokoro TTS models</span>
          <button
            v-if="health.kokoro.status === 'error' && !downloadingKokoro && !health.loading"
            class="ml-auto shrink-0 text-[0.78em] px-[0.7em] py-[0.2em] rounded border border-primary bg-transparent text-primary cursor-pointer whitespace-nowrap hover:bg-primary hover:text-white transition-colors duration-150"
            @click="downloadKokoro"
          >
            Download
          </button>
        </div>

        <div v-if="health.kokoro.status === 'error' || downloadingKokoro" class="flex flex-col gap-[0.3rem] pl-[1.8rem]">
          <div v-for="file in kokoroFileList" :key="file.name" class="flex items-center gap-2">
            <span class="w-[1.2em] flex items-center justify-center shrink-0">
              <span v-if="file.ok" class="icon-done">✓</span>
              <span v-else class="icon-error">✗</span>
            </span>
            <span class="text-[0.85em] text-gray-500 dark:text-gray-400 flex gap-[0.3rem] items-baseline">
              {{ file.name }}
              <span v-if="downloadingKokoro && kokoroCurrentFile === file.name" class="text-[0.85em] text-gray-400">
                {{ kokoroCurrentPercent }}%
              </span>
            </span>
          </div>
        </div>
      </template>
    </div>

    <!-- File Selection -->
    <div class="flex items-center gap-4">
      <label
        class="inline-block px-[1.2em] py-[0.6em] rounded-lg border border-transparent bg-white dark:bg-[#0f0f0f98] dark:text-white shadow-sm text-[1em] font-medium transition-[border-color] duration-[0.25s]"
        :class="allRequirementsOk ? 'cursor-pointer hover:border-primary' : 'opacity-45 cursor-not-allowed'"
      >
        Select Document
        <input type="file" accept=".pdf" :disabled="!allRequirementsOk" @change="onFileChange" hidden />
      </label>
      <span v-if="selectedFile" class="text-[0.9em] text-gray-500 truncate max-w-[200px]">{{ selectedFile.name }}</span>
    </div>

    <!-- Output Directory -->
    <div v-if="selectedFile" class="flex flex-col gap-2">
      <div class="flex flex-col gap-[0.2rem]">
        <label class="text-[0.75em] font-semibold uppercase tracking-[0.05em] text-gray-400">Output folder</label>
        <div class="flex gap-[0.4rem]">
          <input
            :value="outBaseDir"
            class="w-full px-[0.7em] py-[0.45em] rounded-md border border-gray-300 dark:border-gray-600 text-[0.88em] font-mono bg-transparent text-inherit min-w-0 focus:outline-none opacity-55 cursor-default select-none"
            type="text"
            placeholder="/Users/you/MakeDocTalk/docs"
            readonly
          />
          <button
            class="shrink-0 px-[0.8em] py-[0.45em] rounded-md border border-gray-300 bg-transparent text-inherit text-[0.88em] cursor-pointer whitespace-nowrap hover:border-primary hover:text-primary"
            @click="browseFolder"
          >Open</button>
        </div>
      </div>
      <input
        v-model="outName"
        class="w-full px-[0.7em] py-[0.45em] rounded-md border border-gray-300 dark:border-gray-600 text-[0.88em] font-mono bg-transparent text-inherit min-w-0 focus:outline-none focus:border-primary"
        type="text"
        placeholder="my-document"
      />
      <span class="text-[0.8em] font-mono text-gray-400 break-all">→ {{ outBaseDir }}/{{ outName }}</span>
    </div>

    <!-- Convert Button -->
    <div class="flex items-center gap-3">
      <button
        class="px-[1.4em] py-[0.7em] rounded-lg border border-transparent bg-primary text-white text-[1em] font-semibold cursor-pointer transition-opacity duration-200 disabled:opacity-45 disabled:cursor-not-allowed enabled:hover:opacity-85"
        :disabled="!selectedFile || !allRequirementsOk"
        @click="startConversion"
      >
        Convert to Speech
      </button>
    </div>
  </main>
</template>
