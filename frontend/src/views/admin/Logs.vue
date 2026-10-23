<template>
  <div class="page-container">
    <h2 class="page-title">AI 调用日志</h2>
    <div class="filter-row">
      <el-select v-model="feature" placeholder="全部功能" clearable @change="load" style="width:140px">
        <el-option label="情感陪伴" value="companion" />
        <el-option label="内容生成" value="generate" />
        <el-option label="日记总结" value="summary" />
        <el-option label="RAG智能体" value="rag" />
      </el-select>
    </div>
    <el-table :data="logs" stripe size="small">
      <el-table-column prop="id" label="ID" width="50" />
      <el-table-column prop="feature" label="功能" width="90">
        <template #default="{ row }">{{ featureText(row.feature) }}</template>
      </el-table-column>
      <el-table-column prop="user_id" label="用户" width="60" />
      <el-table-column prop="input_text" label="输入" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="70">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="150">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../../api'

const logs = ref([])
const feature = ref('')

const formatTime = (iso) => new Date(iso).toLocaleString('zh-CN')
const featureText = (f) => ({ companion: '情感陪伴', generate: '内容生成', summary: '日记总结', rag: 'RAG智能体' }[f] || f)

const load = async () => {
  logs.value = await adminApi.aiLogs({ feature: feature.value, limit: 100 })
}

onMounted(load)
</script>

<style scoped>
.filter-row {
  margin-bottom: 12px;
}
</style>
