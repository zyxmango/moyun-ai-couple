<template>
  <div class="ai-page">
    <div class="ai-header">
      <h2 class="page-title">旅游记录智能体</h2>
      <div class="header-actions">
        <el-button text size="small" @click="showHistory = true">历史</el-button>
        <el-button text size="small" @click="newChat">新对话</el-button>
        <el-button text size="small" @click="showDocs = true">文档库</el-button>
      </div>
    </div>

    <div class="chat-area" ref="chatBox">
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">✈</div>
        <p>上传旅游文档，用自然语言回顾你们的旅程</p>
        <el-upload :show-file-list="false" :before-upload="uploadDoc" accept=".txt,.md,.json">
          <el-button type="primary" size="small">上传旅游文档</el-button>
        </el-upload>
      </div>
      <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="{ mine: msg.role === 'user' }">
        <div class="avatar" :class="msg.role">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
        <div class="bubble-wrap">
          <div class="bubble" :class="{ mine: msg.role === 'user' }">{{ msg.content }}</div>
          <div v-if="msg.sources && msg.sources.length" class="sources">
            <div class="src-label">来源溯源：</div>
            <el-tag v-for="(s, i) in msg.sources" :key="i" size="small" type="info" effect="plain" class="src-tag">
              {{ s.source }} ({{ s.score }})
            </el-tag>
          </div>
        </div>
      </div>
      <div v-if="loading" class="msg-row">
        <div class="avatar assistant">AI</div>
        <div class="bubble typing">检索知识库中...</div>
      </div>
    </div>

    <div class="input-area">
      <el-input v-model="input" placeholder="问问你们的旅游记录..." @keyup.enter="send" />
      <el-button type="rose" @click="send" :loading="loading" :disabled="!input.trim()">发送</el-button>
    </div>

    <el-drawer v-model="showDocs" title="旅游文档库" size="80%">
      <div class="doc-actions">
        <el-button type="primary" size="small" @click="showEditor = true">写文档</el-button>
        <el-upload :show-file-list="false" :before-upload="uploadDoc" accept=".txt,.md,.json">
          <el-button type="primary" size="small">上传文件</el-button>
        </el-upload>
      </div>
      <div class="doc-list">
        <div v-for="d in docs" :key="d.id" class="doc-item">
          <div>
            <div class="doc-name">{{ d.filename }}</div>
            <div class="doc-meta">{{ d.chunk_count }} 个切片 · {{ formatTime(d.created_at) }}</div>
          </div>
          <el-button text size="small" type="danger" @click="delDoc(d)">删除</el-button>
        </div>
        <div v-if="docs.length === 0" class="empty-doc">暂无文档</div>
      </div>
    </el-drawer>

    <!-- 对话历史抽屉 -->
    <el-drawer v-model="showHistory" title="对话历史" size="75%">
      <div class="history-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="history-item"
          :class="{ active: c.id === conversationId }"
          @click="selectConversation(c)"
        >
          <div class="hist-title">{{ c.title || '未命名对话' }}</div>
          <div class="hist-time">{{ formatTime(c.created_at) }}</div>
        </div>
        <div v-if="conversations.length === 0" class="empty-history">暂无历史对话</div>
      </div>
    </el-drawer>

    <!-- 写文档对话框 -->
    <el-dialog v-model="showEditor" title="写文档" width="90%">
      <el-form label-position="top">
        <el-form-item label="文档标题">
          <el-input v-model="docForm.title" placeholder="如：三亚浪漫之旅" />
        </el-form-item>
        <el-form-item label="文档内容">
          <el-input
            v-model="docForm.content"
            type="textarea"
            :rows="10"
            placeholder="写下你们的旅游记录、攻略、回忆..."
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditor = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDoc">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { ragApi } from '../../api'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const conversationId = ref(null)
const chatBox = ref(null)
const showDocs = ref(false)
const docs = ref([])
const showEditor = ref(false)
const saving = ref(false)
const docForm = ref({ title: '', content: '' })
const showHistory = ref(false)
const conversations = ref([])

const formatTime = (iso) => new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })

const scrollDown = () => {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

const send = async () => {
  const q = input.value.trim()
  if (!q || loading.value) return
  input.value = ''
  messages.value.push({ id: Date.now(), role: 'user', content: q })
  loading.value = true
  scrollDown()
  try {
    const res = await ragApi.chat({ question: q, conversation_id: conversationId.value })
    conversationId.value = res.conversation_id
    messages.value.push({ id: Date.now() + 1, role: 'assistant', content: res.answer, sources: res.sources })
    scrollDown()
    loadConversations()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提问失败')
  } finally {
    loading.value = false
  }
}

const newChat = () => {
  messages.value = []
  conversationId.value = null
}

const selectConversation = (c) => {
  conversationId.value = c.id
  messages.value = c.messages || []
  showHistory.value = false
  scrollDown()
}

const loadConversations = async () => {
  try {
    conversations.value = await ragApi.history({})
  } catch (e) {
    // noop
  }
}

const uploadDoc = async (file) => {
  try {
    const res = await ragApi.upload(file)
    ElMessage.success(`上传成功，已切分为 ${res.chunk_count} 片`)
    loadDocs()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '文档上传失败（仅支持 .txt/.md/.json 文本类文件）')
  }
  return false
}

const saveDoc = async () => {
  if (!docForm.value.content.trim()) {
    ElMessage.warning('请输入文档内容')
    return
  }
  saving.value = true
  try {
    const res = await ragApi.uploadText({
      title: docForm.value.title,
      content: docForm.value.content,
    })
    ElMessage.success(`保存成功，已切分为 ${res.chunk_count} 片`)
    docForm.value = { title: '', content: '' }
    showEditor.value = false
    loadDocs()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const delDoc = async (d) => {
  try {
    await ragApi.deleteDoc(d.id)
    ElMessage.success('已删除')
    loadDocs()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

const loadDocs = async () => {
  try {
    docs.value = await ragApi.documents()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载文档列表失败')
  }
}

const loadHistory = async () => {
  await loadConversations()
  if (conversations.value.length > 0) {
    const latest = conversations.value[0]
    conversationId.value = latest.id
    messages.value = latest.messages || []
    scrollDown()
  }
}

onMounted(() => {
  loadDocs()
  loadHistory()
})
</script>

<style scoped>
.ai-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-width: 720px;
  margin: 0 auto;
}
.ai-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-soft);
}
.header-actions {
  display: flex;
  gap: 4px;
}
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.welcome {
  text-align: center;
  margin-top: 20%;
}
.welcome-icon {
  font-size: 48px;
}
.welcome p {
  color: var(--ink-secondary);
  margin: 12px 0 20px;
}
.msg-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.msg-row.mine {
  flex-direction: row-reverse;
}
.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  flex-shrink: 0;
}
.avatar.user {
  background: var(--ink-dark);
  color: #fff;
}
.avatar.assistant {
  background: var(--accent-rose-bg);
  color: var(--accent-rose);
}
.bubble-wrap {
  max-width: 75%;
}
.bubble {
  padding: 10px 14px;
  border-radius: 14px;
  background: var(--bg-card);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  box-shadow: var(--shadow-soft);
}
.bubble.mine {
  background: var(--accent-rose);
  color: #fff;
}
.sources {
  margin-top: 8px;
}
.src-label {
  font-size: 11px;
  color: var(--ink-light);
  margin-bottom: 4px;
}
.src-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}
.typing {
  color: var(--ink-light);
  font-style: italic;
}
.input-area {
  padding: 10px 12px;
  background: var(--bg-card);
  border-top: 1px solid var(--border-soft);
  display: flex;
  gap: 8px;
}
.doc-list {
  margin-top: 16px;
}
.doc-actions {
  display: flex;
  gap: 10px;
}
.doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid var(--border-soft);
}
.doc-name {
  font-size: 14px;
  color: var(--ink-primary);
}
.doc-meta {
  font-size: 12px;
  color: var(--ink-light);
  margin-top: 4px;
}
.empty-doc {
  text-align: center;
  color: var(--ink-light);
  padding: 30px;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.history-item {
  padding: 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  cursor: pointer;
  transition: background 0.2s;
}
.history-item.active {
  background: var(--accent-rose-bg);
  border-left: 3px solid var(--accent-rose);
}
.history-item:hover {
  background: var(--border-soft);
}
.hist-title {
  font-size: 14px;
  color: var(--ink-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hist-time {
  font-size: 12px;
  color: var(--ink-light);
  margin-top: 4px;
}
.empty-history {
  text-align: center;
  color: var(--ink-light);
  padding: 40px;
}
</style>
