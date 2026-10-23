<template>
  <router-view v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </router-view>
</template>

<script setup>
import { onMounted } from 'vue'
import { useUserStore } from './stores/user'

const store = useUserStore()
onMounted(async () => {
  if (store.token) {
    await store.fetchUser()
  }
})
</script>
