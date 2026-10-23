<template>
  <div class="page-container">
    <h2 class="page-title">数据概览</h2>
    <div class="stat-grid">
      <div v-for="item in statList" :key="item.label" class="ink-card stat-card">
        <div class="stat-num">{{ item.value }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '../../api'

const stats = ref({})
const statList = computed(() => [
  { label: '用户总数', value: stats.value.users || 0 },
  { label: '活跃情侣', value: stats.value.couples_active || 0 },
  { label: '情侣总数', value: stats.value.couples_total || 0 },
  { label: '聊天消息', value: stats.value.messages || 0 },
  { label: '情侣日记', value: stats.value.diaries || 0 },
  { label: '共享照片', value: stats.value.photos || 0 },
  { label: '纪念日', value: stats.value.anniversaries || 0 },
  { label: 'AI 调用', value: stats.value.ai_calls || 0 },
  { label: 'RAG 文档', value: stats.value.documents || 0 },
])

onMounted(async () => {
  stats.value = await adminApi.stats()
})
</script>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.stat-card {
  text-align: center;
  padding: 18px 10px;
}
.stat-num {
  font-size: 26px;
  font-weight: 700;
  color: var(--accent-rose);
}
.stat-label {
  font-size: 12px;
  color: var(--ink-secondary);
  margin-top: 6px;
}
</style>
