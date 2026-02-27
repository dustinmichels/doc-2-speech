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
