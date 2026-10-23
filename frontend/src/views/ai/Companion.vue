<template>
  <div class="ai-page">
    <div class="ai-header">
      <h2 class="page-title">AI 情感陪伴</h2>
      <div class="header-actions">
        <el-button text size="small" @click="showHistory = true">历史</el-button>
        <el-button text size="small" @click="newChat">新对话</el-button>
      </div>
    </div>

    <div class="chat-area" ref="chatBox">
      <div v-if="messages.length === 0" class="welcome">
        <div class="welcome-icon">♥</div>
        <p>和 AI 聊聊你的心情吧</p>
        <div class="suggest-tags">
          <el-tag v-for="s in suggestions" :key="s" @click="quickSend(s)" class="tag" effect="plain">{{ s }}</el-tag>
        </div>
      </div>
      <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="{ mine: msg.role === 'user' }">
        <div class="avatar" :class="msg.role">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
        <div class="bubble" :class="{ mine: msg.role === 'user' }">{{ msg.content }}</div>
      </div>
      <div v-if="loading" class="msg-row">
        <div class="avatar assistant">AI</div>
        <div class="bubble typing">思考中...</div>
      </div>
    </div>

    <div class="input-area">
      <el-input v-model="input" placeholder="说点什么..." @keyup.enter="send" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" />
      <el-button type="rose" @click="send" :loading="loading" :disabled="!input.trim()">发送</el-button>
    </div>

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
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi } from '../../api'

const messages = ref([])
const input = ref('')
const loading = ref(false)
const conversationId = ref(null)
const chatBox = ref(null)
const showHistory = ref(false)
const conversations = ref([])
const suggestions = ['今天有点不开心', '想给对方一个惊喜', '我们吵架了怎么办', '异地恋好难熬']

const formatTime = (iso) => new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })

const scrollDown = () => {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

const send = async (text) => {
  const content = (typeof text === 'string' && text) ? text : input.value.trim()
  if (!content || loading.value) return
  input.value = ''
  messages.value.push({ id: Date.now(), role: 'user', content })
  loading.value = true
  scrollDown()
  try {
    const res = await aiApi.companionChat({ user_message: content, conversation_id: conversationId.value })
    conversationId.value = res.conversation_id
    messages.value.push(res.message)
    scrollDown()
    loadConversations()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '对话失败')
  } finally {
    loading.value = false
  }
}

const quickSend = (s) => send(s)

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
    conversations.value = await aiApi.companionHistory({})
  } catch (e) {
    // noop
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

onMounted(loadHistory)
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
  color: var(--accent-rose);
}
.welcome p {
  color: var(--ink-secondary);
  margin: 12px 0 20px;
}
.suggest-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.tag {
  cursor: pointer;
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
.bubble {
  max-width: 75%;
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
  align-items: flex-end;
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
