<template>
  <div class="page-container memory-page">
    <header class="page-head">
      <div>
        <h2>共同记忆库</h2>
        <p>管理右下角情侣助手可以记住的聊天、日记、照片与纪念日</p>
      </div>
      <el-button v-if="settings.enabled" :loading="syncing" @click="syncAll">同步记忆</el-button>
    </header>

    <div v-if="loading" class="ink-card loading-card"><el-skeleton :rows="6" animated /></div>

    <section v-else-if="!settings.enabled" class="ink-card consent-card">
      <div class="consent-icon">✦</div>
      <h3>由你们决定 AI 可以记住什么</h3>
      <p>开启后，系统会在当前情侣关系内建立共同记忆索引。记忆不会与其他情侣共享，并可随时清空。</p>
      <div class="source-switches">
        <label><span>聊天文字</span><el-switch v-model="settings.include_chat" /></label>
        <label><span>共同日记</span><el-switch v-model="settings.include_diary" /></label>
        <label><span>相册记录</span><el-switch v-model="settings.include_album" /></label>
        <label><span>纪念日</span><el-switch v-model="settings.include_anniversary" /></label>
      </div>
      <el-button type="primary" class="enable-btn" :loading="saving" @click="enableMemory">同意并开启共同记忆</el-button>
    </section>

    <el-tabs v-else v-model="activeTab" class="memory-tabs">
      <el-tab-pane label="记忆问答" name="ask">
        <section class="ink-card ask-card">
          <div class="starter-list" v-if="!messages.length">
            <p>可以这样问</p>
            <button v-for="item in starters" :key="item" @click="question = item">{{ item }}</button>
          </div>
          <div v-for="(item, index) in messages" :key="index" class="message" :class="item.role">
            <div v-if="item.role === 'assistant'" class="assistant-name"><span>♥</span> 共同记忆助手</div>
            <div class="bubble">{{ item.content }}</div>
          </div>
          <div class="ask-input">
            <el-input v-model="question" placeholder="询问你们的共同经历…" @keyup.enter="ask" />
            <el-button type="primary" :loading="asking" @click="ask">提问</el-button>
          </div>
        </section>
      </el-tab-pane>

      <el-tab-pane label="记录偏好" name="capture">
        <section class="ink-card capture-card">
          <div class="capture-head">
            <div><h3>告诉 AI 一件值得记住的事</h3><p>可以记录饮食偏好、约会习惯、未来计划或一段共同经历。</p></div>
            <el-tag effect="plain">支持版本更新</el-tag>
          </div>
          <el-form label-position="top">
            <el-form-item label="标题"><el-input v-model="manual.title" placeholder="例如：我的饮食偏好" /></el-form-item>
            <el-form-item label="内容"><el-input v-model="manual.content" type="textarea" :rows="4" placeholder="例如：现在胃不太舒服，约会吃饭尽量少辣" /></el-form-item>
            <div class="capture-row">
              <el-form-item label="类型">
                <el-select v-model="manual.category"><el-option label="偏好" value="preference" /><el-option label="共同事件" value="event" /><el-option label="未来计划" value="plan" /></el-select>
              </el-form-item>
              <el-form-item label="可见范围">
                <el-radio-group v-model="manual.visibility"><el-radio-button label="shared">双方共享</el-radio-button><el-radio-button label="private">仅自己可见</el-radio-button></el-radio-group>
              </el-form-item>
            </div>
            <p class="privacy-tip">私密记忆只会参与你发起的问答和规划，对方无法查看或检索。</p>
            <el-button type="primary" :loading="savingManual" @click="saveManual">保存记忆</el-button>
          </el-form>
        </section>
      </el-tab-pane>

      <el-tab-pane label="记忆时间线" name="timeline">
        <div class="toolbar">
          <span>共 {{ memories.total }} 条共同记忆</span>
          <el-select v-model="sourceFilter" clearable placeholder="全部来源" @change="loadMemories">
            <el-option label="聊天事件" value="chat_event" />
            <el-option label="日记" value="diary" />
            <el-option label="相册" value="photo" />
            <el-option label="纪念日" value="anniversary" />
          </el-select>
        </div>
        <el-empty v-if="!memories.items.length" description="同步后，共同记忆会出现在这里" />
        <div v-else class="timeline-list">
          <article v-for="item in memories.items" :key="item.id" class="ink-card memory-card">
            <div class="memory-date">{{ formatDate(item.event_date || item.created_at) }}</div>
            <div class="memory-main">
              <div class="memory-title">
                <strong>{{ item.title }}</strong>
                <el-tag size="small" effect="plain">{{ sourceLabel(item.source_type) }}</el-tag>
                <el-tag v-if="item.visibility === 'private'" size="small" type="warning" effect="plain">仅自己可见</el-tag>
                <el-tag v-if="item.status === 'uncertain'" size="small" type="info" effect="plain">信息不确定</el-tag>
                <el-tag v-if="item.version > 1" size="small" effect="plain">v{{ item.version }}</el-tag>
              </div>
              <p>{{ item.content }}</p>
              <div class="memory-meta">
                <span v-if="item.location">📍 {{ item.location }}</span>
                <span v-if="item.emotion">心情：{{ item.emotion }}</span>
                <span v-for="tag in item.tags" :key="tag">#{{ tag }}</span>
              </div>
            </div>
            <div class="memory-actions">
              <el-button text @click="editMemory(item)">纠正</el-button>
              <el-button text type="danger" @click="removeMemory(item)">删除</el-button>
            </div>
          </article>
        </div>
      </el-tab-pane>

      <el-tab-pane label="每日互动" name="daily">
        <section v-if="daily" class="ink-card daily-card">
          <div class="daily-date">{{ daily.date }}</div>
          <h3>{{ daily.question }}</h3>
          <template v-if="!daily.answered">
            <el-input v-model="dailyAnswer" type="textarea" :rows="4" placeholder="写下你的真实想法，对方回答后才能互相查看" />
            <el-button type="primary" :loading="answering" @click="submitDaily">提交回答</el-button>
          </template>
          <template v-else>
            <div class="my-answer"><b>我的回答</b><p>{{ daily.my_answer }}</p></div>
            <div v-if="!daily.both_answered" class="waiting">答案已保存，等待对方回答后解锁 ✦</div>
            <div v-else class="answer-grid">
              <div v-for="(answer, index) in daily.answers" :key="answer.user_id">
                <b>{{ index === 0 ? '回答一' : '回答二' }}</b>
                <p>{{ answer.content }}</p>
              </div>
            </div>
          </template>
        </section>
      </el-tab-pane>

      <el-tab-pane label="恋爱周报" name="report">
        <section class="ink-card report-card">
          <div class="report-actions">
            <div><h3>共同记忆周报</h3><p>只依据真实记录生成，不进行感情打分</p></div>
            <el-button type="primary" :loading="reporting" @click="generateReport">生成本周周报</el-button>
          </div>
          <div v-if="report" class="report-content">
            <div class="report-count">本次参考 {{ report.memory_count }} 条记忆</div>
            <p>{{ report.content }}</p>
          </div>
        </section>
      </el-tab-pane>

      <el-tab-pane label="隐私设置" name="privacy">
        <section class="ink-card privacy-card">
          <h3>数据来源</h3>
          <label><span>同步聊天文字</span><el-switch v-model="settings.include_chat" /></label>
          <label><span>同步共同日记</span><el-switch v-model="settings.include_diary" /></label>
          <label><span>同步相册记录</span><el-switch v-model="settings.include_album" /></label>
          <label><span>同步纪念日</span><el-switch v-model="settings.include_anniversary" /></label>
          <el-button type="primary" :loading="saving" @click="saveSettings">保存设置</el-button>
          <el-divider />
          <h3>关闭与清理</h3>
          <p>关闭后停止同步，但保留现有记忆。你也可以彻底清空 AI 记忆索引，原始聊天、日记和照片不会被删除。</p>
          <el-button @click="disableMemory">关闭 AI 记忆</el-button>
          <el-button type="danger" plain @click="clearMemories">清空 AI 记忆</el-button>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { memoryApi } from '../../api'

const loading = ref(true)
const saving = ref(false)
const syncing = ref(false)
const asking = ref(false)
const answering = ref(false)
const reporting = ref(false)
const savingManual = ref(false)
const activeTab = ref('ask')
const sourceFilter = ref('')
const question = ref('')
const conversationId = ref(null)
const messages = ref([])
const daily = ref(null)
const dailyAnswer = ref('')
const report = ref(null)
const memories = reactive({ total: 0, items: [] })
const settings = reactive({ enabled: false, include_chat: true, include_diary: true, include_album: true, include_anniversary: true })
const manual = reactive({ title: '', content: '', category: 'preference', visibility: 'shared' })
const starters = ['我们第一次旅行是什么时候？', '最近有哪些值得纪念的开心事情？', '我们讨论过哪些未来计划？']

const formatDate = (value) => value ? new Date(value).toLocaleDateString('zh-CN') : '日期未记录'
const sourceLabel = (type) => ({ chat_event: '聊天事件', diary: '日记', photo: '相册', anniversary: '纪念日', manual: '主动记录' }[type] || type)

const loadSettings = async () => Object.assign(settings, await memoryApi.settings())
const loadMemories = async () => Object.assign(memories, await memoryApi.list({ status: 'all', source_type: sourceFilter.value || undefined }))
const loadDaily = async () => { daily.value = await memoryApi.todayQuestion() }

const loadWorkspace = async () => {
  await Promise.all([loadMemories(), loadDaily()])
}

const enableMemory = async () => {
  saving.value = true
  try {
    settings.enabled = true
    Object.assign(settings, await memoryApi.updateSettings({ ...settings }))
    await loadWorkspace()
    ElMessage.success('共同记忆已开启')
  } finally { saving.value = false }
}

const saveSettings = async () => {
  saving.value = true
  try {
    Object.assign(settings, await memoryApi.updateSettings({ ...settings }))
    await loadMemories()
    ElMessage.success('设置已保存')
  } finally { saving.value = false }
}

const disableMemory = async () => {
  settings.enabled = false
  await memoryApi.updateSettings({ ...settings })
  ElMessage.success('AI 共同记忆已关闭')
}

const syncAll = async () => {
  syncing.value = true
  try {
    const result = await memoryApi.sync()
    await loadMemories()
    ElMessage.success(`同步完成，共 ${result.total} 条记忆`)
  } finally { syncing.value = false }
}

const saveManual = async () => {
  if (!manual.title.trim() || !manual.content.trim()) return ElMessage.warning('请填写标题和内容')
  savingManual.value = true
  try {
    await memoryApi.createManual({ ...manual })
    manual.title = ''
    manual.content = ''
    await loadMemories()
    activeTab.value = 'timeline'
    ElMessage.success(manual.visibility === 'private' ? '私密记忆已保存' : '共享记忆已保存')
  } finally { savingManual.value = false }
}

const ask = async () => {
  const text = question.value.trim()
  if (!text || asking.value) return
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  asking.value = true
  try {
    const result = await memoryApi.chat({ question: text, conversation_id: conversationId.value })
    conversationId.value = result.conversation_id
    messages.value.push({ role: 'assistant', content: result.answer })
  } finally { asking.value = false }
}

const submitDaily = async () => {
  if (!dailyAnswer.value.trim()) return ElMessage.warning('请先写下回答')
  answering.value = true
  try {
    daily.value = await memoryApi.answerQuestion(daily.value.id, dailyAnswer.value)
    dailyAnswer.value = ''
    ElMessage.success('回答已保存')
  } finally { answering.value = false }
}

const generateReport = async () => {
  reporting.value = true
  try { report.value = await memoryApi.report(7) } finally { reporting.value = false }
}

const removeMemory = async (item) => {
  await ElMessageBox.confirm(`确定删除“${item.title}”的 AI 记忆索引？`, '删除记忆')
  await memoryApi.delete(item.id)
  await loadMemories()
}

const editMemory = async (item) => {
  const { value } = await ElMessageBox.prompt('纠正这条记忆的内容。保存后会作为确定信息参与回答。', '纠正记忆', {
    inputValue: item.content,
    inputType: 'textarea',
    confirmButtonText: '保存',
    cancelButtonText: '取消',
    inputValidator: value => value?.trim() ? true : '内容不能为空'
  })
  await memoryApi.review(item.id, { status: 'confirmed', content: value.trim() })
  await loadMemories()
  ElMessage.success('记忆已纠正')
}

const clearMemories = async () => {
  await ElMessageBox.confirm('只清空 AI 索引，不删除原始聊天、日记或照片。确定继续？', '清空 AI 记忆', { type: 'warning' })
  await memoryApi.clear()
  await loadMemories()
  ElMessage.success('AI 记忆已清空')
}

onMounted(async () => {
  try {
    await loadSettings()
    if (settings.enabled) await loadWorkspace()
  } finally { loading.value = false }
})
</script>

<style scoped>
.memory-page { max-width: 820px; }
.page-head { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:18px; }
.page-head h2 { margin:0; font-size:24px; color:var(--ink-darkest); }
.page-head p { margin:6px 0 0; font-size:13px; color:var(--ink-secondary); }
.loading-card,.consent-card,.ask-card,.daily-card,.report-card,.privacy-card,.capture-card { padding:24px; }
.consent-card { max-width:560px; margin:40px auto; text-align:center; }
.consent-icon { font-size:38px; color:var(--accent-rose); }
.consent-card h3 { margin:8px 0; }
.consent-card > p,.privacy-card > p { color:var(--ink-secondary); line-height:1.8; font-size:13px; }
.source-switches { margin:20px 0; text-align:left; }
.source-switches label,.privacy-card label { display:flex; justify-content:space-between; padding:13px 0; border-bottom:1px solid var(--border-soft); }
.enable-btn { width:100%; }
.memory-tabs :deep(.el-tabs__header) { margin-bottom:18px; }
.starter-list { margin-bottom:18px; }
.starter-list p { color:var(--ink-secondary); font-size:13px; }
.starter-list button { display:block; width:100%; border:1px solid var(--border-soft); background:var(--bg-soft); border-radius:10px; padding:10px 12px; margin:8px 0; color:var(--ink-primary); text-align:left; cursor:pointer; }
.message { display:flex; flex-direction:column; margin:12px 0; }
.message.user { align-items:flex-end; }
.assistant-name { display:flex; align-items:center; gap:5px; margin:0 0 6px 4px; color:var(--ink-light); font-size:11px; }
.assistant-name span { color:var(--accent-rose); font-size:12px; }
.bubble { max-width:85%; padding:12px 15px; border-radius:4px 16px 16px 16px; background:var(--bg-soft); color:var(--ink-primary); white-space:pre-wrap; line-height:1.75; }
.message.user .bubble { background:var(--accent-rose); color:#fff; }
.message.user .bubble { border-radius:16px 4px 16px 16px; }
.ask-input { display:flex; gap:8px; margin-top:22px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; color:var(--ink-secondary); font-size:13px; }
.timeline-list { position:relative; }
.memory-card { display:flex; gap:18px; padding:18px; margin-bottom:12px; }
.memory-date { width:92px; flex-shrink:0; font-size:12px; color:var(--ink-light); }
.memory-main { flex:1; min-width:0; }
.memory-actions { display:flex; flex-shrink:0; }
.memory-title { display:flex; align-items:center; gap:8px; }
.memory-main p,.review-card p { color:var(--ink-secondary); line-height:1.7; white-space:pre-wrap; }
.memory-meta { display:flex; gap:10px; flex-wrap:wrap; font-size:11px; color:var(--ink-light); }
.daily-card { text-align:center; max-width:600px; margin:auto; }
.daily-date { color:var(--accent-rose); font-size:12px; }
.daily-card h3 { margin:14px 0 24px; font-size:20px; line-height:1.6; }
.daily-card .el-button { margin-top:14px; width:100%; }
.my-answer,.answer-grid > div { margin-top:12px; padding:16px; background:var(--bg-soft); border-radius:12px; text-align:left; }
.waiting { margin-top:16px; color:var(--ink-secondary); }
.answer-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
.report-actions { display:flex; justify-content:space-between; align-items:center; gap:16px; }
.report-actions h3 { margin:0; }.report-actions p { margin:5px 0 0; color:var(--ink-secondary); font-size:12px; }
.report-content { margin-top:20px; border-top:1px solid var(--border-soft); padding-top:18px; }
.report-content p { white-space:pre-wrap; line-height:2; }
.report-count { font-size:12px; color:var(--ink-light); }
.review-card { padding:18px; margin-bottom:12px; }
.review-card h3 { margin:0; }
.review-actions { display:flex; justify-content:flex-end; margin-top:12px; }
.privacy-card { max-width:600px; margin:auto; }
.privacy-card > .el-button { margin:16px 8px 0 0; }
.capture-card { max-width:680px; margin:auto; }
.capture-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:18px; }
.capture-head h3 { margin:0; }.capture-head p { margin:6px 0 0; color:var(--ink-secondary); font-size:12px; }
.capture-row { display:grid; grid-template-columns:180px 1fr; gap:16px; }
.privacy-tip { margin:-4px 0 16px; color:var(--ink-light); font-size:12px; line-height:1.6; }
@media (max-width:600px) { .page-head,.report-actions { align-items:flex-start; flex-direction:column; }.memory-card { flex-direction:column; gap:8px; }.memory-date { width:auto; }.answer-grid,.capture-row { grid-template-columns:1fr; } }
</style>
