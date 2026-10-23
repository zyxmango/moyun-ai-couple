<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">情侣日记</h2>
      <el-button type="primary" size="small" @click="openCreate">写日记</el-button>
    </div>

    <div v-if="list.length === 0" class="empty">还没有日记，记录你们的故事</div>

    <div v-for="d in list" :key="d.id" class="ink-card diary-card">
      <div class="diary-top">
        <div class="diary-title">{{ d.title || '无题' }}</div>
        <el-tag v-if="d.mood" size="small" effect="plain">{{ d.mood }}</el-tag>
      </div>
      <div class="diary-content">{{ d.content }}</div>
      <div class="diary-meta">
        <span>{{ d.author_nickname }} · {{ formatTime(d.created_at) }}</span>
        <div>
          <el-button text size="small" @click="editItem(d)">编辑</el-button>
          <el-button text size="small" type="danger" @click="del(d)">删除</el-button>
        </div>
      </div>
    </div>

    <el-dialog v-model="showDialog" :title="editId ? '编辑日记' : '写日记'" width="90%">
      <el-form :model="form" label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="给这篇日记起个标题" />
        </el-form-item>
        <el-form-item label="心情">
          <el-select v-model="form.mood" placeholder="选择心情" clearable style="width:100%">
            <el-option label="开心" value="开心" />
            <el-option label="平静" value="平静" />
            <el-option label="感动" value="感动" />
            <el-option label="思念" value="思念" />
            <el-option label="小确幸" value="小确幸" />
            <el-option label="有点难过" value="有点难过" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="6" placeholder="记录此刻的心情..." />
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
import { diaryApi } from '../../api'

const list = ref([])
const showDialog = ref(false)
const editId = ref(null)
const form = ref({ title: '', content: '', mood: '' })

const formatTime = (iso) => {
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const load = async () => {
  try {
    list.value = await diaryApi.list()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载日记失败')
  }
}

const openCreate = () => {
  editId.value = null
  form.value = { title: '', content: '', mood: '' }
  showDialog.value = true
}

const editItem = (d) => {
  editId.value = d.id
  form.value = { title: d.title, content: d.content, mood: d.mood }
  showDialog.value = true
}

const save = async () => {
  if (!form.value.content) {
    ElMessage.warning('请输入日记内容')
    return
  }
  try {
    if (editId.value) {
      await diaryApi.update(editId.value, form.value)
    } else {
      await diaryApi.create(form.value)
    }
    ElMessage.success('保存成功')
    showDialog.value = false
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  }
}

const del = async (d) => {
  try {
    await ElMessageBox.confirm('确定删除这篇日记？', '提示')
  } catch { return }
  try {
    await diaryApi.delete(d.id)
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
.diary-card {
  margin-bottom: 12px;
}
.diary-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.diary-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.diary-content {
  font-size: 14px;
  color: var(--ink-primary);
  line-height: 1.7;
  white-space: pre-wrap;
  max-height: 120px;
  overflow: hidden;
}
.diary-meta {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--ink-light);
}
</style>
