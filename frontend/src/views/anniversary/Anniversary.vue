<template>
  <div class="page-container anniversary-page">
    <header class="page-header">
      <div>
        <span class="eyebrow">OUR MOMENTS</span>
        <h2 class="page-title">值得记住的日子</h2>
        <p class="page-subtitle">把相遇、约定和共同经历，留在时间里。</p>
      </div>
      <button class="add-button" type="button" @click="openCreate">
        <el-icon><Plus /></el-icon><span>添加</span>
      </button>
    </header>

    <div v-if="list.length === 0" class="empty">
      <div class="empty-mark">♡</div>
      <h3>还没有特别的日子</h3>
      <p>从第一次见面、第一次旅行开始记录吧。</p>
      <button type="button" @click="openCreate">添加第一个纪念日</button>
    </div>

    <div v-else class="anniversary-list">
      <article v-for="item in list" :key="item.id" class="ann-card">
        <div class="card-glow"></div>
        <div class="date-stamp" aria-hidden="true">
          <span>{{ dateParts(item.date).month }}月</span>
          <strong>{{ dateParts(item.date).day }}</strong>
          <small>{{ dateParts(item.date).year }}</small>
        </div>

        <div class="ann-main">
          <div class="ann-heading">
            <div>
              <span class="ann-kicker">纪念日 · 每年</span>
              <h3>{{ item.title }}</h3>
            </div>
            <div v-if="item.days_until !== null" class="ann-count" :class="{ today: item.days_until === 0 }">
              <strong>{{ item.days_until === 0 ? '今天' : item.days_until }}</strong>
              <span v-if="item.days_until !== 0">天后</span>
            </div>
          </div>

          <p v-if="item.description" class="ann-desc">{{ item.description }}</p>
          <p v-else class="ann-desc muted">这一天的故事，等你们慢慢补充。</p>

          <footer class="ann-footer">
            <div class="reminder-state" :class="{ enabled: item.reminder_enabled }">
              <span class="state-dot"></span>
              {{ item.reminder_enabled ? '小忆会提前提醒' : '暂未开启提醒' }}
            </div>
            <div class="ann-actions">
              <button type="button" @click="editItem(item)">
                <el-icon><EditPen /></el-icon><span>编辑</span>
              </button>
              <button class="delete" type="button" @click="deleteItem(item)" aria-label="删除纪念日">
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </footer>
        </div>
      </article>
    </div>

    <el-dialog
      v-model="showDialog"
      width="min(92vw, 520px)"
      top="7vh"
      append-to-body
      align-center
      class="anniversary-dialog"
      @closed="resetForm"
    >
      <template #header>
        <div class="dialog-heading">
          <div class="dialog-mark"><el-icon><Calendar /></el-icon></div>
          <div>
            <span>{{ editId ? 'EDIT A MOMENT' : 'NEW MOMENT' }}</span>
            <h3>{{ editId ? '编辑纪念日' : '收藏一个特别的日子' }}</h3>
          </div>
        </div>
      </template>

      <p class="dialog-intro">多年以后再回头看，普通的一天也会因为你们的故事而闪闪发亮。</p>
      <el-form :model="form" label-position="top" class="anniversary-form">
        <el-form-item label="这一天叫什么">
          <el-input v-model="form.title" maxlength="60" placeholder="例如：第一次见面" />
        </el-form-item>
        <el-form-item label="发生在什么时候">
          <el-date-picker
            v-model="form.date"
            type="date"
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
            format="YYYY年 MM月 DD日"
            style="width:100%"
          />
        </el-form-item>
        <el-form-item label="关于这一天的故事">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="300"
            show-word-limit
            placeholder="写下一句以后看到还会微笑的话……"
          />
        </el-form-item>
        <div class="reminder-setting">
          <div class="reminder-icon"><el-icon><Bell /></el-icon></div>
          <div class="reminder-copy">
            <strong>让小忆提前提醒</strong>
            <span>临近这一天时，会出现在你们的智能提醒中。</span>
          </div>
          <el-switch v-model="form.reminder_enabled" />
        </div>
      </el-form>

      <template #footer>
        <div class="dialog-actions">
          <el-button class="cancel-button" @click="showDialog = false">以后再说</el-button>
          <el-button class="save-button" :loading="saving" @click="save">
            <el-icon><Check /></el-icon>
            <span>{{ editId ? '保存修改' : '收藏这一天' }}</span>
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Bell, Calendar, Check, Delete, EditPen, Plus } from '@element-plus/icons-vue'
import { anniversaryApi } from '../../api'

const list = ref([])
const showDialog = ref(false)
const editId = ref(null)
const saving = ref(false)
const blankForm = () => ({ title: '', date: '', description: '', reminder_enabled: true })
const form = ref(blankForm())

const dateParts = (date) => {
  const [year = '', month = '', day = ''] = String(date || '').split('-')
  return { year, month: Number(month) || '--', day: day || '--' }
}

const load = async () => {
  try {
    list.value = await anniversaryApi.list()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载纪念日失败')
  }
}

const resetForm = () => {
  editId.value = null
  form.value = blankForm()
}

const openCreate = () => {
  resetForm()
  showDialog.value = true
}

const editItem = (item) => {
  editId.value = item.id
  form.value = {
    title: item.title,
    date: item.date,
    description: item.description || '',
    reminder_enabled: item.reminder_enabled,
  }
  showDialog.value = true
}

const save = async () => {
  if (!form.value.title.trim() || !form.value.date) {
    ElMessage.warning('请填写标题和日期')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value, title: form.value.title.trim(), description: form.value.description.trim() }
    if (editId.value) await anniversaryApi.update(editId.value, payload)
    else await anniversaryApi.create(payload)
    ElMessage.success(editId.value ? '纪念日已更新' : '已经替你们收藏好了')
    showDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const deleteItem = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除「${item.title}」？`, '删除纪念日', {
      confirmButtonText: '确定删除', cancelButtonText: '保留', type: 'warning',
    })
  } catch { return }
  try {
    await anniversaryApi.delete(item.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.anniversary-page { padding-bottom:34px; }
.page-header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin:4px 0 24px; }
.eyebrow { color:var(--accent-rose); font-family:Georgia,serif; font-size:10px; font-weight:700; letter-spacing:2.4px; }
.page-title { margin:7px 0 5px; font-family:Georgia,'Songti SC',serif; font-size:26px; letter-spacing:.5px; }
.page-subtitle { margin:0; color:var(--ink-secondary); font-size:12px; line-height:1.65; }
.add-button { flex:0 0 auto; display:flex; align-items:center; gap:6px; margin-top:7px; padding:9px 13px; border:0; border-radius:999px; color:#fff; background:linear-gradient(135deg,#d68181,var(--accent-rose)); box-shadow:0 7px 18px rgba(201,107,107,.22); font-size:12px; cursor:pointer; }
.add-button:hover { transform:translateY(-1px); box-shadow:0 9px 22px rgba(201,107,107,.28); }
.anniversary-list { display:grid; gap:14px; }
.ann-card { position:relative; display:flex; gap:18px; overflow:hidden; padding:20px; border:1px solid var(--card-border); border-radius:20px; background:var(--card-surface); box-shadow:var(--shadow-card); }
.card-glow { position:absolute; top:-70px; right:-45px; width:160px; height:160px; border-radius:50%; background:radial-gradient(circle,rgba(232,180,180,.24),rgba(250,240,240,0) 70%); pointer-events:none; }
.date-stamp { position:relative; flex:0 0 70px; height:88px; display:flex; flex-direction:column; align-items:center; justify-content:center; border:1px solid rgba(201,169,110,.24); border-radius:18px; color:var(--accent-rose); background:linear-gradient(160deg,#fff9f6,#f8eee9); box-shadow:inset 0 0 0 4px rgba(255,255,255,.45); }
.date-stamp span { font-size:10px; font-weight:700; letter-spacing:1.3px; }
.date-stamp strong { margin:2px 0 0; font-family:Georgia,serif; font-size:28px; font-weight:500; line-height:1; }
.date-stamp small { margin-top:5px; color:var(--ink-light); font-size:9px; letter-spacing:1px; }
.ann-main { position:relative; min-width:0; flex:1; }
.ann-heading { display:flex; justify-content:space-between; gap:12px; }
.ann-kicker { color:var(--accent-gold); font-size:9px; font-weight:700; letter-spacing:1.5px; }
.ann-heading h3 { margin:5px 0 0; color:var(--ink-darkest); font-family:'Songti SC','STSong',serif; font-size:18px; line-height:1.35; }
.ann-count { flex:0 0 auto; display:flex; align-items:baseline; gap:3px; height:40px; color:var(--accent-rose); }
.ann-count strong { font-family:Georgia,serif; font-size:29px; font-weight:500; line-height:1; }
.ann-count span { color:var(--ink-light); font-size:10px; }
.ann-count.today strong { padding:6px 10px; border-radius:999px; background:var(--accent-rose-bg); font-family:inherit; font-size:13px; }
.ann-desc { min-height:22px; margin:11px 0 14px; color:var(--ink-secondary); font-size:12px; line-height:1.7; }
.ann-desc.muted { color:var(--ink-light); }
.ann-footer { display:flex; align-items:center; justify-content:space-between; gap:12px; padding-top:12px; border-top:1px solid rgba(232,228,222,.8); }
.reminder-state { display:flex; align-items:center; gap:7px; color:var(--ink-light); font-size:10px; }
.state-dot { width:6px; height:6px; border-radius:50%; background:#c8c4be; box-shadow:0 0 0 3px rgba(154,154,154,.08); }
.reminder-state.enabled { color:var(--accent-teal); }
.reminder-state.enabled .state-dot { background:var(--accent-teal); box-shadow:0 0 0 3px rgba(94,139,126,.12); }
.ann-actions { display:flex; align-items:center; gap:4px; }
.ann-actions button { display:flex; align-items:center; gap:4px; padding:5px 7px; border:0; border-radius:8px; color:var(--ink-secondary); background:transparent; font-size:10px; cursor:pointer; }
.ann-actions button:hover { color:var(--ink-darkest); background:var(--bg-soft); }
.ann-actions button.delete { padding:6px; color:#b9908b; }
.ann-actions button.delete:hover { color:var(--accent-rose); background:var(--accent-rose-bg); }
.empty { margin-top:70px; padding:40px 24px; border:1px dashed var(--border-soft); border-radius:22px; text-align:center; background:rgba(255,255,255,.55); }
.empty-mark { width:52px; height:52px; display:grid; place-items:center; margin:0 auto 14px; border-radius:18px; color:var(--accent-rose); background:var(--accent-rose-bg); font-size:26px; }
.empty h3 { color:var(--ink-darkest); font-size:16px; }.empty p { margin:8px 0 20px; color:var(--ink-secondary); font-size:12px; }
.empty button { border:0; border-radius:999px; padding:9px 16px; color:#fff; background:var(--accent-rose); cursor:pointer; }
.dialog-heading { display:flex; align-items:center; gap:13px; }
.dialog-mark { width:46px; height:46px; display:grid; place-items:center; flex:0 0 auto; border-radius:16px; color:var(--accent-rose); background:linear-gradient(145deg,#fbe9e9,#fff7f2); font-size:20px; }
.dialog-heading span { color:var(--accent-gold); font-family:Georgia,serif; font-size:9px; font-weight:700; letter-spacing:1.8px; }
.dialog-heading h3 { margin:4px 0 0; color:var(--ink-darkest); font-family:'Songti SC','STSong',serif; font-size:19px; }
.dialog-intro { margin:0 0 20px; padding:12px 14px; border-left:2px solid var(--accent-rose-light); color:var(--ink-secondary); background:linear-gradient(90deg,var(--accent-rose-bg),transparent); font-size:11px; line-height:1.7; }
.reminder-setting { display:flex; align-items:center; gap:11px; margin-top:2px; padding:14px; border:1px solid var(--border-soft); border-radius:14px; background:var(--bg-paper); }
.reminder-icon { width:34px; height:34px; display:grid; place-items:center; flex:0 0 auto; border-radius:11px; color:var(--accent-gold); background:#f7efe2; }
.reminder-copy { min-width:0; flex:1; }.reminder-copy strong,.reminder-copy span { display:block; }
.reminder-copy strong { color:var(--ink-primary); font-size:12px; }.reminder-copy span { margin-top:3px; color:var(--ink-light); font-size:9px; line-height:1.5; }
.dialog-actions { display:flex; justify-content:flex-end; gap:9px; }
.dialog-actions .cancel-button { border-color:transparent; color:var(--ink-secondary); background:var(--bg-soft); }
.dialog-actions .save-button { border:0; color:#fff; background:linear-gradient(135deg,#d88484,var(--accent-rose)); box-shadow:0 7px 17px rgba(201,107,107,.2); }

:global(.anniversary-dialog.el-dialog) { overflow:hidden; border-radius:24px; background:#fffdfb; box-shadow:0 28px 70px rgba(44,35,32,.2); }
:global(.anniversary-dialog .el-dialog__header) { margin:0; padding:22px 24px 13px; border-bottom:0; }
:global(.anniversary-dialog .el-dialog__headerbtn) { top:18px; right:18px; width:34px; height:34px; border-radius:50%; }
:global(.anniversary-dialog .el-dialog__headerbtn:hover) { background:var(--bg-soft); }
:global(.anniversary-dialog .el-dialog__body) { padding:8px 24px 4px; }
:global(.anniversary-dialog .el-dialog__footer) { padding:18px 24px 22px; }
:global(.anniversary-dialog .el-form-item) { margin-bottom:18px; }
:global(.anniversary-dialog .el-form-item__label) { padding-bottom:7px; color:var(--ink-secondary); font-size:11px; font-weight:600; }
:global(.anniversary-dialog .el-input__wrapper) { min-height:42px; border-radius:11px; background:var(--bg-paper); box-shadow:0 0 0 1px var(--border-soft) inset; }
:global(.anniversary-dialog .el-input__wrapper.is-focus) { background:#fff; box-shadow:0 0 0 1px var(--accent-rose-light) inset; }
:global(.anniversary-dialog .el-textarea__inner) { border:0; border-radius:11px; padding:11px 13px; background:var(--bg-paper); box-shadow:0 0 0 1px var(--border-soft) inset; line-height:1.7; resize:none; }
:global(.anniversary-dialog .el-textarea__inner:focus) { background:#fff; box-shadow:0 0 0 1px var(--accent-rose-light) inset; }
:global(.anniversary-dialog .el-switch.is-checked .el-switch__core) { border-color:var(--accent-rose); background:var(--accent-rose); }

@media (max-width: 520px) {
  .anniversary-page { padding:14px 12px 30px; }
  .page-header { margin-bottom:19px; }.page-title { font-size:23px; }.page-subtitle { max-width:240px; }
  .add-button { padding:8px 11px; }.add-button span { display:none; }
  .ann-card { gap:12px; padding:15px 14px; border-radius:18px; }
  .date-stamp { flex-basis:58px; height:76px; border-radius:15px; }.date-stamp strong { font-size:24px; }
  .ann-heading h3 { font-size:16px; }.ann-count strong { font-size:25px; }
  .ann-desc { margin:9px 0 12px; font-size:11px; }
  .ann-footer { align-items:flex-end; }.reminder-state { max-width:130px; line-height:1.4; }
  :global(.anniversary-dialog.el-dialog) { width:calc(100vw - 24px) !important; border-radius:21px; }
  :global(.anniversary-dialog .el-dialog__header) { padding:19px 18px 11px; }
  :global(.anniversary-dialog .el-dialog__body) { padding:7px 18px 2px; }
  :global(.anniversary-dialog .el-dialog__footer) { padding:16px 18px 19px; }
  .dialog-mark { width:42px; height:42px; }.dialog-heading h3 { font-size:17px; }
  .dialog-actions .el-button { flex:1; margin:0; }
}
</style>
