<template>
  <div class="page-container">
    <h2 class="page-title">用户管理</h2>
    <el-table :data="users" stripe size="small">
      <el-table-column prop="id" label="ID" width="50" />
      <el-table-column prop="phone" label="手机号" width="130" />
      <el-table-column prop="nickname" label="昵称" />
      <el-table-column label="情侣" width="70">
        <template #default="{ row }">
          <el-tag v-if="row.couple_id" size="small" type="success">已绑定</el-tag>
          <el-tag v-else size="small" type="info">未绑定</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="管理员" width="70">
        <template #default="{ row }">
          <el-tag v-if="row.is_admin" size="small" type="danger">管理员</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi } from '../../api'

const users = ref([])
onMounted(async () => {
  users.value = await adminApi.users()
})
</script>
