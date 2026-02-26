<script setup lang="ts">
import { ref } from "vue";
import HomePage from "./HomePage.vue";
import RunningPage from "./RunningPage.vue";

const isRunning = ref(false);
const conversionConfig = ref<{ file: File; outBaseDir: string; outName: string } | null>(null);

function onStart(file: File, outBaseDir: string, outName: string) {
  conversionConfig.value = { file, outBaseDir, outName };
  isRunning.value = true;
}

function onBack() {
  isRunning.value = false;
  conversionConfig.value = null;
}
</script>

<template>
  <HomePage v-if="!isRunning" @start="onStart" />
  <RunningPage
    v-else
    :file="conversionConfig!.file"
    :out-base-dir="conversionConfig!.outBaseDir"
    :out-name="conversionConfig!.outName"
    @back="onBack"
  />
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
