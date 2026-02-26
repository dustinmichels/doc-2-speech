<script setup lang="ts">
import { ref, computed } from "vue";
import { openUrl } from "@tauri-apps/plugin-opener";

const props = defineProps<{ ollamaInstalled: boolean }>();
const emit = defineEmits<{ back: []; statusUpdated: [ok: boolean, detail: string] }>();

const BASE = "http://localhost:8000";
const checking = ref(false);
const localStatus = ref<{ ok: boolean; detail: string; found_models?: string[] } | null>(null);

const isInstalled = computed(() => localStatus.value?.ok ?? props.ollamaInstalled);
const foundModels = computed(() => localStatus.value?.found_models ?? []);

const models = [
  {
    tier: "Light",
    model_name: "qwen3:1.7b",
    size: "1.2 GB",
    requirement: "4GB+ RAM / Older Laptops",
    description:
      "Ultra-fast and incredibly efficient. Ideal for basic grammar correction and rewriting on the go without draining battery or slowing down other apps.",
  },
  {
    tier: "Standard",
    model_name: "llama3.2:3b",
    size: "2.0 GB",
    requirement: "8GB+ RAM / Modern Laptops",
    description:
      "The best balance of speed and intelligence. It is highly optimized for instruction-following, making it very reliable at maintaining the original meaning while improving prose.",
  },
  {
    tier: "Power",
    model_name: "gemma3:12b",
    size: "8.0 GB",
    requirement: "16GB+ RAM / Desktop or Pro Laptops",
    description:
      "A significantly smarter model that understands nuance, complex tone, and flow. Use this for high-quality professional editing where the user has a dedicated GPU or high-speed RAM.",
  },
];

const allModels = [
  "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b",
  "llama3.2:1b", "llama3.2:3b", "llama4:8b",
  "gemma3:1b", "gemma3:4b", "gemma3:12b",
  "phi3.5:latest", "phi4:14b", "phi4-mini-instruct",
  "mistral:7b", "mistral-small3.2:24b",
  "smollm3:3b", "liquid-lfm:1.2b", "lfm2.5-thinking:1.2b",
  "granite4:1b", "granite4:3b",
  "deepseek-v3.2-exp:7b",
  "ministral-3:3b", "ministral-3:8b",
  "glm-4.7-flash", "rnj-1:8b",
];

const selectedTier = ref("Standard");
const showMore = ref(false);
const selectedModel = computed(() => models.find((m) => m.tier === selectedTier.value)!);

const copied = ref(false);

async function copyCommand() {
  await navigator.clipboard.writeText(`ollama pull ${selectedModel.value.model_name}`);
  copied.value = true;
  setTimeout(() => (copied.value = false), 2000);
}

function goInstall() {
  openUrl("https://ollama.com/download");
}

async function recheck() {
  checking.value = true;
  try {
    const res = await fetch(`${BASE}/health/ollama`);
    const data = await res.json();
    localStatus.value = { ok: data.ok, detail: data.detail, found_models: data.found_models ?? [] };
    emit("statusUpdated", data.ok, data.detail);
  } catch {
    const detail = "Cannot reach backend server";
    localStatus.value = { ok: false, detail };
    emit("statusUpdated", false, detail);
  } finally {
    checking.value = false;
  }
}
</script>

<template>
  <main class="container">
    <button class="back-btn" @click="emit('back')">← Back</button>

    <h1>Ollama Setup</h1>

    <ol class="instructions">
      <li>
        <a href="#" @click.prevent="goInstall">Install Ollama</a>
      </li>
      <li>
        Once installed, choose a model and run the command in your terminal.

        <div class="tier-tabs">
          <button
            v-for="m in models"
            :key="m.tier"
            class="tier-tab"
            :class="{ active: !showMore && selectedTier === m.tier }"
            @click="showMore = false; selectedTier = m.tier"
          >
            {{ m.tier }}
          </button>
          <button
            class="tier-tab"
            :class="{ active: showMore }"
            @click="showMore = !showMore"
          >
            More
          </button>
        </div>

        <template v-if="!showMore">
          <div class="model-card">
            <div class="model-meta">
              <span class="model-name">{{ selectedModel.model_name }}</span>
              <span class="model-badge">{{ selectedModel.size }}</span>
              <span class="model-badge muted">{{ selectedModel.requirement }}</span>
            </div>
            <p class="model-description">{{ selectedModel.description }}</p>
          </div>

          <button class="code-block" @click="copyCommand">
            <span>ollama pull {{ selectedModel.model_name }}</span>
            <span class="copy-icon">{{ copied ? "✓" : "⎘" }}</span>
          </button>
        </template>

        <template v-else>
          <p class="more-intro">There are other downloadable models you could try as well. For example:</p>
          <ul class="more-models">
            <li v-for="m in allModels" :key="m"><code>{{ m }}</code></li>
          </ul>
        </template>
      </li>
    </ol>

    <div class="status-section">
      <div class="status-row">
        <span class="status-icon">
          <span v-if="checking" class="spinner"></span>
          <span v-else-if="isInstalled" class="icon-done">✓</span>
          <span v-else class="icon-error">✗</span>
        </span>
        <span class="status-text">
          <span v-if="checking">Checking…</span>
          <span v-else-if="isInstalled">
            Ready — found
            <span v-for="(m, i) in foundModels" :key="m">
              <code>{{ m }}</code><span v-if="i < foundModels.length - 1">, </span>
            </span>
          </span>
          <span v-else>No supported model found. Pull one using the command above.</span>
        </span>
      </div>
      <div class="status-actions">
        <button class="recheck-btn" :disabled="checking" @click="recheck">
          {{ checking ? "Checking…" : "Re-check" }}
        </button>
      </div>
    </div>
  </main>
</template>

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

.back-btn {
  align-self: flex-start;
  padding: 0.3em 0.8em;
  border-radius: 6px;
  border: 1px solid #ccc;
  background: transparent;
  cursor: pointer;
  font-size: 0.9em;
  color: inherit;
}

.back-btn:hover {
  border-color: #396cd8;
  color: #396cd8;
}

.instructions {
  font-size: 0.95em;
  line-height: 1.6;
  margin: 0;
  padding-left: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.code-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 0.75rem;
  padding: 0.6em 1em;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.06);
  font-family: monospace;
  font-size: 0.9em;
  white-space: pre;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  cursor: pointer;
  color: inherit;
  transition: border-color 0.15s;
}

.code-block:hover {
  border-color: #396cd8;
}

@media (prefers-color-scheme: dark) {
  .code-block {
    background: rgba(255, 255, 255, 0.08);
  }
}

.copy-icon {
  font-size: 1em;
  opacity: 0.5;
  flex-shrink: 0;
  transition: opacity 0.15s;
}

.code-block:hover .copy-icon {
  opacity: 1;
}

.status-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.04);
}

@media (prefers-color-scheme: dark) {
  .status-section {
    background: rgba(255, 255, 255, 0.06);
  }
}

.status-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.9em;
}

.status-icon {
  width: 1.2em;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
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

.status-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.recheck-btn {
  padding: 0.4em 0.9em;
  border-radius: 6px;
  border: 1px solid #ccc;
  background: transparent;
  cursor: pointer;
  font-size: 0.85em;
  color: inherit;
}

.recheck-btn:hover:not(:disabled) {
  border-color: #396cd8;
  color: #396cd8;
}

.recheck-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.install-btn {
  padding: 0.4em 1em;
  border-radius: 6px;
  border: 1px solid transparent;
  background-color: #396cd8;
  color: #fff;
  font-size: 0.85em;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.install-btn:hover {
  opacity: 0.85;
}

.tier-tabs {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.tier-tab {
  padding: 0.35em 0.9em;
  border-radius: 6px;
  border: 1px solid #ccc;
  background: transparent;
  cursor: pointer;
  font-size: 0.85em;
  color: inherit;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.tier-tab:hover {
  border-color: #396cd8;
  color: #396cd8;
}

.tier-tab.active {
  border-color: #396cd8;
  background: #396cd8;
  color: #fff;
}

.model-card {
  margin-top: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

@media (prefers-color-scheme: dark) {
  .model-card {
    background: rgba(255, 255, 255, 0.06);
  }
}

.model-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.model-name {
  font-family: monospace;
  font-size: 0.9em;
  font-weight: 600;
}

.model-badge {
  font-size: 0.78em;
  padding: 0.15em 0.55em;
  border-radius: 4px;
  background: rgba(57, 108, 216, 0.15);
  color: #396cd8;
}

.model-badge.muted {
  background: rgba(0, 0, 0, 0.06);
  color: inherit;
  opacity: 0.7;
}

@media (prefers-color-scheme: dark) {
  .model-badge.muted {
    background: rgba(255, 255, 255, 0.08);
  }
}

.model-description {
  margin: 0;
  font-size: 0.85em;
  line-height: 1.5;
  opacity: 0.8;
}

.more-intro {
  margin: 0.75rem 0 0;
  font-size: 0.85em;
  opacity: 0.7;
  line-height: 1.5;
}

.more-models {
  margin: 0.5rem 0 0 1rem;
  padding: 0 0.5rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.85em;
  max-height: 180px;
  overflow-y: auto;
}
</style>
