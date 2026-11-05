<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">情侣日记</h2>
      <el-button type="primary" size="small" @click="openCreate">写日记</el-button>
    </div>

    <div v-if="list.length === 0" class="empty">还没有日记，记录你们的故事</div>

    <article v-for="d in list" :key="d.id" class="diary-card">
      <header class="diary-top">
        <h3 class="diary-title">{{ d.title || '无题' }}</h3>
        <span v-if="d.mood" class="mood-chip"><i aria-hidden="true"></i>{{ d.mood }}</span>
      </header>
      <p class="diary-content">{{ d.content }}</p>
      <footer class="diary-meta">
        <div class="author-line">
          <span class="author-mark" aria-hidden="true">{{ authorInitial(d.author_nickname) }}</span>
          <span class="author-name">{{ d.author_nickname }}</span>
          <time>{{ formatTime(d.created_at) }}</time>
        </div>
        <div class="diary-actions">
          <button type="button" @click="editItem(d)">编辑</button>
          <button type="button" class="delete" @click="del(d)">删除</button>
        </div>
      </footer>
    </article>

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

const authorInitial = (name) => (name || '我').trim().slice(0, 1)

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
  position: relative;
  margin-bottom: 14px;
  padding: 20px 20px 15px;
  overflow: hidden;
  border: 1px solid rgba(174, 143, 125, 0.22);
  border-radius: 22px;
  background:
    radial-gradient(circle at 100% 0, rgba(210, 137, 137, 0.13), transparent 38%),
    linear-gradient(145deg, rgba(255, 252, 248, 0.98), rgba(247, 240, 233, 0.94));
  box-shadow: 0 10px 28px rgba(75, 55, 45, 0.07), inset 0 1px rgba(255, 255, 255, 0.82);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}
.diary-card::before {
  content: '';
  position: absolute;
  top: 24px;
  left: 0;
  width: 3px;
  height: 30px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, var(--accent-rose), #d7a48c);
  opacity: 0.72;
}
.diary-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(75, 55, 45, 0.09), inset 0 1px rgba(255, 255, 255, 0.86);
}
.diary-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 11px;
}
.diary-title {
  min-width: 0;
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  line-height: 1.45;
  letter-spacing: 0.01em;
  color: var(--ink-darkest);
}
.mood-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 27px;
  padding: 0 10px;
  border-radius: 999px;
  color: #a45f5f;
  background: rgba(201, 107, 107, 0.1);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
.mood-chip i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.72;
}
.diary-content {
  margin: 0;
  font-size: 14px;
  color: var(--ink-primary);
  line-height: 1.85;
  white-space: pre-wrap;
  max-height: 120px;
  overflow: hidden;
}
.diary-meta {
  margin-top: 15px;
  padding-top: 12px;
  border-top: 1px solid rgba(143, 113, 96, 0.12);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--ink-light);
}
.author-line {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.author-mark {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #a96863;
  background: rgba(201, 107, 107, 0.11);
  font-size: 11px;
  font-weight: 700;
}
.author-name {
  max-width: 80px;
  overflow: hidden;
  color: var(--ink-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.author-line time::before {
  content: '·';
  margin-right: 6px;
  color: rgba(120, 99, 88, 0.4);
}
.diary-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.diary-actions button {
  border: 0;
  border-radius: 9px;
  padding: 6px 9px;
  color: var(--ink-secondary);
  background: transparent;
  font: inherit;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease;
}
.diary-actions button:hover {
  color: var(--ink-darkest);
  background: rgba(95, 76, 66, 0.07);
}
.diary-actions .delete {
  color: #ba7772;
}
.diary-actions .delete:hover {
  color: #ad5555;
  background: rgba(201, 107, 107, 0.09);
}
@media (max-width: 390px) {
  .diary-card { padding: 18px 17px 14px; }
  .diary-meta { align-items: flex-end; }
  .author-line { flex-wrap: wrap; row-gap: 2px; }
  .author-line time { width: calc(100% - 30px); margin-left: 30px; }
  .author-line time::before { display: none; }
}
</style>
