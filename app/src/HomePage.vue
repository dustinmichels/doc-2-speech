<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from "vue";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import OllamaInstructions from "./OllamaInstructions.vue";
import { BASE, consumeSSE } from "./utils";

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

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  if (selectedFile.value) {
    outBaseDir.value = "~/MakeDocTalk/docs";
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
  <main v-else class="container">
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
          <button
            v-if="health.ollama.status === 'error' && !health.loading"
            class="download-btn"
            @click="showOllamaInstructions = true"
          >
            Install
          </button>
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
      <label class="file-btn" :class="{ disabled: !allRequirementsOk }">
        Select Document
        <input type="file" accept=".pdf" :disabled="!allRequirementsOk" @change="onFileChange" hidden />
      </label>
      <span v-if="selectedFile" class="filename">{{ selectedFile.name }}</span>
    </div>

    <div v-if="selectedFile" class="outdir-section">
      <div class="outdir-field">
        <label class="outdir-label">Output folder</label>
        <div class="outdir-input-row">
          <input
            :value="outBaseDir"
            class="outdir-input outdir-input--readonly"
            type="text"
            placeholder="~/MakeDocTalk/docs"
            readonly
          />
          <button class="browse-btn" @click="browseFolder">Open</button>
        </div>
      </div>
      <input
        v-model="outName"
        class="outdir-input"
        type="text"
        placeholder="my-document"
      />
      <span class="outdir-preview">→ {{ outBaseDir }}/{{ outName }}</span>
    </div>

    <div class="convert-row">
      <button
        class="convert-btn"
        :disabled="!selectedFile || !allRequirementsOk"
        @click="startConversion"
      >
        Convert to Speech
      </button>
    </div>
  </main>
</template>

<style scoped>
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

.file-btn:hover:not(.disabled) {
  border-color: #396cd8;
}

.file-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.filename {
  font-size: 0.9em;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.outdir-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.outdir-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.outdir-label {
  font-size: 0.75em;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #888;
}

.outdir-input-row {
  display: flex;
  gap: 0.4rem;
}

.outdir-input {
  width: 100%;
  padding: 0.45em 0.7em;
  border-radius: 6px;
  border: 1px solid #ccc;
  font-size: 0.88em;
  font-family: monospace;
  background: transparent;
  color: inherit;
  box-sizing: border-box;
  min-width: 0;
}

.outdir-input:focus {
  outline: none;
  border-color: #396cd8;
}

.outdir-input:disabled {
  opacity: 0.5;
}

.outdir-input--readonly {
  opacity: 0.55;
  cursor: default;
  user-select: none;
}

.outdir-input--readonly:focus {
  border-color: #ccc;
}

@media (prefers-color-scheme: dark) {
  .outdir-input {
    border-color: #555;
  }
}

.browse-btn {
  flex-shrink: 0;
  padding: 0.45em 0.8em;
  border-radius: 6px;
  border: 1px solid #ccc;
  background: transparent;
  color: inherit;
  font-size: 0.88em;
  cursor: pointer;
  white-space: nowrap;
}

.browse-btn:hover:not(:disabled) {
  border-color: #396cd8;
  color: #396cd8;
}

.browse-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.outdir-preview {
  font-size: 0.8em;
  font-family: monospace;
  color: #888;
  word-break: break-all;
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

.convert-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.convert-btn:not(:disabled):hover {
  opacity: 0.85;
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
