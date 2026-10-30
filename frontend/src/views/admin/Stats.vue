<template>
  <div class="page-container">
    <h2 class="page-title">数据概览</h2>
    <div class="stat-grid">
      <div v-for="item in statList" :key="item.label" class="ink-card stat-card">
        <div class="stat-num">{{ item.value }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </div>
    <h2 class="section-title">长期记忆运行状态</h2>
    <div class="stat-grid memory-grid">
      <div v-for="item in memoryList" :key="item.label" class="ink-card stat-card">
        <div class="stat-num" :class="{ danger: item.danger }">{{ item.value }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { adminApi } from '../../api'

const stats = ref({})
const memory = ref({ jobs: {}, last_24h: {} })
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
const memoryList = computed(() => [
  { label: '待处理消息', value: memory.value.message_lag_total || 0, danger: memory.value.message_lag_total > 0 },
  { label: '失败任务', value: memory.value.jobs?.failed || 0, danger: memory.value.jobs?.failed > 0 },
  { label: '待生成向量', value: memory.value.unembedded_memories || 0, danger: memory.value.unembedded_memories > 0 },
  { label: '24h 失败率', value: `${((memory.value.last_24h?.failure_rate || 0) * 100).toFixed(1)}%`, danger: memory.value.last_24h?.failure_rate > 0 },
  { label: '同步中位耗时', value: `${Math.round(memory.value.last_24h?.duration_median_ms || 0)} ms` },
  { label: '24h 模型调用', value: memory.value.last_24h?.model_calls || 0 },
  { label: '24h 输入 Token', value: memory.value.last_24h?.input_tokens || 0 },
  { label: '24h 估算成本', value: `$${Number(memory.value.last_24h?.estimated_cost_usd || 0).toFixed(4)}` },
  { label: '同步报错情侣', value: memory.value.couples_with_sync_error || 0, danger: memory.value.couples_with_sync_error > 0 },
])

onMounted(async () => {
  const [overview, memoryHealth] = await Promise.all([adminApi.stats(), adminApi.memoryHealth()])
  stats.value = overview
  memory.value = memoryHealth
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
.section-title { margin:26px 0 14px; font-size:18px; }
.stat-num.danger { color:#d35d5d; }
@media (max-width:700px) { .stat-grid { grid-template-columns:repeat(2,1fr); } }
</style>
