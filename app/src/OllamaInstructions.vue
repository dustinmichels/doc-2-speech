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
  <main class="max-w-[480px] mx-auto pt-[10vh] px-8 pb-8 flex flex-col gap-6">
    <button
      class="self-start px-[0.8em] py-[0.3em] rounded-md border border-gray-300 bg-transparent cursor-pointer text-[0.9em] text-inherit hover:border-primary hover:text-primary"
      @click="emit('back')"
    >← Back</button>

    <h1 class="text-[1.8rem] font-semibold">Ollama Setup</h1>

    <ol class="text-[0.95em] leading-[1.6] m-0 pl-5 flex flex-col gap-2">
      <li>
        <a href="#" class="text-primary" @click.prevent="goInstall">Install Ollama</a>
      </li>
      <li>
        Once installed, choose a model and run the command in your terminal.

        <div class="flex gap-2 mt-3">
          <button
            v-for="m in models"
            :key="m.tier"
            class="px-[0.9em] py-[0.35em] rounded-md border text-[0.85em] cursor-pointer transition-all duration-150"
            :class="!showMore && selectedTier === m.tier
              ? 'border-primary bg-primary text-white'
              : 'border-gray-300 bg-transparent text-inherit hover:border-primary hover:text-primary'"
            @click="showMore = false; selectedTier = m.tier"
          >
            {{ m.tier }}
          </button>
          <button
            class="px-[0.9em] py-[0.35em] rounded-md border text-[0.85em] cursor-pointer transition-all duration-150"
            :class="showMore
              ? 'border-primary bg-primary text-white'
              : 'border-gray-300 bg-transparent text-inherit hover:border-primary hover:text-primary'"
            @click="showMore = !showMore"
          >
            More
          </button>
        </div>

        <template v-if="!showMore">
          <div class="mt-3 px-4 py-3 rounded-lg bg-black/[0.04] dark:bg-white/[0.06] flex flex-col gap-[0.4rem]">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-mono text-[0.9em] font-semibold">{{ selectedModel.model_name }}</span>
              <span class="text-[0.78em] px-[0.55em] py-[0.15em] rounded bg-primary/15 text-primary">{{ selectedModel.size }}</span>
              <span class="text-[0.78em] px-[0.55em] py-[0.15em] rounded bg-black/[0.06] dark:bg-white/[0.08] opacity-70">{{ selectedModel.requirement }}</span>
            </div>
            <p class="m-0 text-[0.85em] leading-[1.5] opacity-80">{{ selectedModel.description }}</p>
          </div>

          <button
            class="group flex items-center justify-between gap-3 mt-3 px-[1em] py-[0.6em] rounded-md bg-black/[0.06] dark:bg-white/[0.08] font-mono text-[0.9em] whitespace-pre w-full text-left border border-transparent cursor-pointer text-inherit transition-[border-color] duration-150 hover:border-primary"
            @click="copyCommand"
          >
            <span>ollama pull {{ selectedModel.model_name }}</span>
            <span class="opacity-50 shrink-0 transition-opacity duration-150 group-hover:opacity-100">{{ copied ? "✓" : "⎘" }}</span>
          </button>
        </template>

        <template v-else>
          <p class="mt-3 mb-0 text-[0.85em] opacity-70 leading-[1.5]">There are other downloadable models you could try as well. For example:</p>
          <ul class="mt-2 ml-4 pr-2 flex flex-col gap-1 text-[0.85em] max-h-[180px] overflow-y-auto list-none p-0">
            <li v-for="m in allModels" :key="m"><code>{{ m }}</code></li>
          </ul>
        </template>
      </li>
    </ol>

    <div class="flex flex-col gap-3 p-4 rounded-lg bg-black/[0.04] dark:bg-white/[0.06]">
      <div class="flex items-center gap-[0.6rem] text-[0.9em]">
        <span class="w-[1.2em] flex items-center justify-center shrink-0">
          <span v-if="checking" class="spinner"></span>
          <span v-else-if="isInstalled" class="icon-done">✓</span>
          <span v-else class="icon-error">✗</span>
        </span>
        <span>
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
      <div class="flex gap-3 items-center">
        <button
          class="px-[0.9em] py-[0.4em] rounded-md border border-gray-300 bg-transparent cursor-pointer text-[0.85em] text-inherit enabled:hover:border-primary enabled:hover:text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="checking"
          @click="recheck"
        >
          {{ checking ? "Checking…" : "Re-check" }}
        </button>
      </div>
    </div>
  </main>
</template>
