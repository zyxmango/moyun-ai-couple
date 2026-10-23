<template>
  <div class="page-container">
    <h2 class="page-title">情侣关系</h2>
    <el-table :data="couples" stripe size="small">
      <el-table-column prop="id" label="ID" width="50" />
      <el-table-column prop="pairing_code" label="配对码" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="user1_nickname" label="用户1" />
      <el-table-column prop="user2_nickname" label="用户2" />
      <el-table-column prop="created_at" label="创建时间" width="150">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../../api'

const couples = ref([])
const formatTime = (iso) => new Date(iso).toLocaleString('zh-CN')
const statusText = (s) => ({ pending: '待配对', active: '已绑定', dissolved: '已解除' }[s] || s)
const statusType = (s) => ({ pending: 'warning', active: 'success', dissolved: 'info' }[s] || '')

onMounted(async () => {
  couples.value = await adminApi.couples()
})
</script>
