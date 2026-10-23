<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">纪念日</h2>
      <el-button type="primary" size="small" @click="showDialog = true">添加</el-button>
    </div>

    <div v-if="list.length === 0" class="empty">还没有纪念日，添加一个吧</div>

    <div v-for="item in list" :key="item.id" class="ink-card ann-card">
      <div class="ann-top">
        <div>
          <div class="ann-title">{{ item.title }}</div>
          <div class="ann-date">{{ item.date }}</div>
        </div>
        <div v-if="item.days_until !== null" class="ann-count">
          <span class="num">{{ item.days_until }}</span>
          <span class="unit">天后</span>
        </div>
      </div>
      <div v-if="item.description" class="ann-desc">{{ item.description }}</div>
      <div class="ann-actions">
        <el-tag :type="item.reminder_enabled ? 'danger' : 'info'" size="small" effect="plain">
          {{ item.reminder_enabled ? '已开启提醒' : '未开启提醒' }}
        </el-tag>
        <el-button text size="small" @click="editItem(item)">编辑</el-button>
        <el-button text size="small" type="danger" @click="deleteItem(item)">删除</el-button>
      </div>
    </div>

    <el-dialog v-model="showDialog" :title="editId ? '编辑纪念日' : '添加纪念日'" width="90%">
      <el-form :model="form" label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="如：恋爱纪念日" />
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="form.date" type="date" placeholder="选择日期" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述这个特别的日子" />
        </el-form-item>
        <el-form-item label="开启提醒">
          <el-switch v-model="form.reminder_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { anniversaryApi } from '../../api'

const list = ref([])
const showDialog = ref(false)
const editId = ref(null)
const form = ref({ title: '', date: '', description: '', reminder_enabled: true })

const load = async () => {
  try {
    list.value = await anniversaryApi.list()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载纪念日失败')
  }
}

const editItem = (item) => {
  editId.value = item.id
  form.value = { title: item.title, date: item.date, description: item.description, reminder_enabled: item.reminder_enabled }
  showDialog.value = true
}

const save = async () => {
  if (!form.value.title || !form.value.date) {
    ElMessage.warning('请填写标题和日期')
    return
  }
  try {
    if (editId.value) {
      await anniversaryApi.update(editId.value, form.value)
    } else {
      await anniversaryApi.create(form.value)
    }
    ElMessage.success('保存成功')
    showDialog.value = false
    editId.value = null
    form.value = { title: '', date: '', description: '', reminder_enabled: true }
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

const deleteItem = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除「${item.title}」？`, '提示')
  } catch { return }
  try {
    await anniversaryApi.delete(item.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.empty {
  text-align: center;
  color: var(--ink-light);
  margin-top: 40%;
  font-size: 15px;
}
.ann-card {
  margin-bottom: 12px;
}
.ann-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ann-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.ann-date {
  font-size: 13px;
  color: var(--ink-secondary);
  margin-top: 4px;
}
.ann-count {
  text-align: center;
}
.ann-count .num {
  font-size: 28px;
  font-weight: 700;
  color: var(--accent-rose);
}
.ann-count .unit {
  font-size: 12px;
  color: var(--ink-secondary);
  margin-left: 2px;
}
.ann-desc {
  margin-top: 10px;
  font-size: 14px;
  color: var(--ink-secondary);
  line-height: 1.6;
}
.ann-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
