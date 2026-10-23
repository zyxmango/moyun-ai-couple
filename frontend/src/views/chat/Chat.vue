<template>
  <div class="chat-page" :style="pageStyle">
    <header class="chat-header">
      <div class="partner-title">
        <strong>{{ partnerName || '私密聊天' }}</strong>
        <span><i></i>{{ totalCount }} 条共同对话</span>
      </div>
      <div class="header-actions">
        <el-date-picker
          v-model="dateSearch"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          :disabled-date="disableFuture"
          popper-class="chat-date-picker"
          class="date-picker"
          @change="jumpToDate"
        />
        <button class="calendar-button" title="按日期查找聊天" @click="openDatePicker">
          <el-icon><Calendar /></el-icon>
        </button>
        <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="badge" />
      </div>
    </header>

    <div v-if="historicalDate" class="history-mode-bar">
      <span>正在查看 {{ formatPickedDate(historicalDate) }} 及之前的记录</span>
      <button @click="loadHistory">回到最新 <span v-if="newMessageCount">· {{ newMessageCount }} 条新消息</span></button>
    </div>

    <div class="chat-messages" ref="msgBox" :style="messagesStyle" @scroll="handleScroll">
      <div v-if="messages.length === 0" class="empty-tip">开始你们的第一次对话吧 ♥</div>
      <div v-else class="history-status">
        <button v-if="hasMoreOlder" :disabled="loadingOlder" @click="loadOlder">
          {{ loadingOlder ? '正在加载…' : '加载更早的消息' }}
        </button>
        <span v-else>已经到最早的消息了</span>
      </div>

      <div v-for="item in displayMessages" :key="item.id" class="message-unit">
        <div v-if="item.showTime" class="time-divider"><span>{{ item.timeLabel }}</span></div>
        <div class="msg-row" :class="{ mine: item.sender_id === store.user.id }">
          <el-avatar class="chat-avatar" :size="38" :src="avatarFor(item)">
            {{ nameFor(item)?.[0] || '?' }}
          </el-avatar>
          <div class="message-content">
            <div class="bubble" :class="{ mine: item.sender_id === store.user.id }">
              <img v-if="item.msg_type === 'image'" :src="assetUrl(item.content)" class="msg-img" />
              <span v-else>{{ item.content }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <button v-if="historicalDate || newMessageCount" class="back-latest" @click="loadHistory">
      <el-icon><Bottom /></el-icon>
      {{ newMessageCount ? `${newMessageCount} 条新消息` : '回到最新' }}
    </button>

    <div class="chat-input">
      <el-upload :show-file-list="false" :before-upload="handleImage" accept="image/*">
        <button class="input-tool" title="发送图片"><el-icon><Picture /></el-icon></button>
      </el-upload>
      <el-input v-model="inputText" placeholder="发消息…" @keyup.enter="send" class="input" />
      <el-button type="primary" @click="send" :disabled="!inputText.trim()">发送</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Bottom, Calendar, Picture } from '@element-plus/icons-vue'
import { API_BASE, assetUrl, chatApi, settingsApi } from '../../api'
import { useUserStore } from '../../stores/user'

const store = useUserStore()
const messages = ref([])
const inputText = ref('')
const msgBox = ref(null)
const unreadCount = ref(0)
const partner = ref(null)
const coupleInfo = ref(null)
const ws = ref(null)
const chatBg = ref('')
const totalCount = ref(0)
const loadingOlder = ref(false)
const hasMoreOlder = ref(true)
const historicalDate = ref('')
const dateSearch = ref('')
const newMessageCount = ref(0)
const pageSize = 100

const partnerName = computed(() => partner.value?.nickname || '')
const ownProfile = computed(() => {
  if (!coupleInfo.value) return store.user
  return coupleInfo.value.is_user1 ? coupleInfo.value.user1 : coupleInfo.value.user2
})

const presets = {
  default: '', cream: 'linear-gradient(135deg, #faf5ec 0%, #faf0f0 100%)',
  mint: 'linear-gradient(135deg, #eef5f2 0%, #edf4f7 100%)',
  sunset: 'linear-gradient(135deg, #faf0f0 0%, #faf5ec 50%, #edf4f7 100%)',
  lavender: 'linear-gradient(135deg, #f1edf7 0%, #f5edf5 100%)',
  ink: 'linear-gradient(135deg, #f7f5f0 0%, #f1edf7 100%)',
}
const messagesStyle = computed(() => {
  if (!chatBg.value) return {}
  if (chatBg.value.startsWith('preset:')) return { background: presets[chatBg.value.slice(7)] || '' }
  return { backgroundImage: `url(${assetUrl(chatBg.value)})`, backgroundSize: 'cover', backgroundPosition: 'center', backgroundAttachment: 'local' }
})
const pageStyle = computed(() => chatBg.value && !chatBg.value.startsWith('preset:') ? { background: 'transparent' } : {})

const dayKey = raw => {
  const date = new Date(raw)
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`
}
const chatTimeLabel = raw => {
  const date = new Date(raw)
  const today = new Date()
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const clock = timeLabel(raw)
  if (dayKey(date) === dayKey(today)) return clock
  if (dayKey(date) === dayKey(yesterday)) return `昨天 ${clock}`
  const sameYear = date.getFullYear() === today.getFullYear()
  return `${sameYear ? '' : `${date.getFullYear()}年`}${date.getMonth() + 1}月${date.getDate()}日 ${clock}`
}
const timeLabel = raw => new Date(raw).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
const displayMessages = computed(() => messages.value.map((message, index) => {
  const previous = messages.value[index - 1]
  const differentDay = !previous || dayKey(previous.created_at) !== dayKey(message.created_at)
  const gap = previous ? new Date(message.created_at) - new Date(previous.created_at) : Infinity
  return {
    ...message,
    showTime: differentDay || gap >= 5 * 60 * 1000,
    timeLabel: differentDay ? chatTimeLabel(message.created_at) : timeLabel(message.created_at),
  }
}))

const avatarFor = item => assetUrl(item.sender_id === store.user.id ? ownProfile.value?.avatar : partner.value?.avatar)
const nameFor = item => item.sender_id === store.user.id ? (ownProfile.value?.nickname || store.user?.nickname) : partnerName.value
const scrollToBottom = () => nextTick(() => { if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight })

const loadHistory = async () => {
  try {
    const [data, countResult] = await Promise.all([chatApi.history({ limit: pageSize }), chatApi.count()])
    messages.value = data
    totalCount.value = countResult.total || data.length
    hasMoreOlder.value = data.length === pageSize
    historicalDate.value = ''
    dateSearch.value = ''
    newMessageCount.value = 0
    scrollToBottom()
  } catch (error) {
    const detail = error?.response?.data?.detail
    if (!detail?.includes('尚未绑定')) ElMessage.error(detail || '加载聊天记录失败')
  }
}

const loadOlder = async () => {
  if (loadingOlder.value || !hasMoreOlder.value || !messages.value.length || !msgBox.value) return
  loadingOlder.value = true
  const box = msgBox.value
  const previousHeight = box.scrollHeight
  try {
    const older = await chatApi.history({ limit: pageSize, before: messages.value[0].created_at })
    const existing = new Set(messages.value.map(item => item.id))
    messages.value = [...older.filter(item => !existing.has(item.id)), ...messages.value]
    hasMoreOlder.value = older.length === pageSize
    await nextTick()
    box.scrollTop = box.scrollHeight - previousHeight
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载更早消息失败')
  } finally { loadingOlder.value = false }
}
const handleScroll = () => { if (msgBox.value?.scrollTop < 60) loadOlder() }

const disableFuture = date => date.getTime() > Date.now()
const openDatePicker = () => document.querySelector('.date-picker input')?.click()
const formatPickedDate = raw => {
  const [year, month, day] = raw.split('-')
  return `${year}年${Number(month)}月${Number(day)}日`
}
const jumpToDate = async value => {
  if (!value) return
  try {
    // 本地所选日期的次日零点，转为带时区的 UTC 边界查询。
    const [year, month, day] = value.split('-').map(Number)
    const before = new Date(year, month - 1, day + 1).toISOString()
    const data = await chatApi.history({ limit: pageSize, before })
    messages.value = data
    historicalDate.value = value
    hasMoreOlder.value = data.length === pageSize
    await nextTick()
    scrollToBottom()
    if (!data.length) ElMessage.info('这一天之前还没有聊天记录')
  } catch (error) { ElMessage.error(error?.response?.data?.detail || '按日期查找失败') }
}

const loadPartner = async () => {
  try {
    const info = await settingsApi.coupleInfo()
    coupleInfo.value = info
    partner.value = info.is_user1 ? info.user2 : info.user1
    chatBg.value = info.chat_bg || ''
  } catch { /* 尚未绑定时由路由处理 */ }
}

const connectWs = () => {
  if (!store.token) return
  const wsHost = API_BASE ? API_BASE.replace(/^https?:\/\//, '') : location.host
  const wsProto = API_BASE.startsWith('https') ? 'wss' : (location.protocol === 'https:' ? 'wss' : 'ws')
  ws.value = new WebSocket(`${wsProto}://${wsHost}/ws/chat/${store.token}`)
  ws.value.onerror = error => console.error('[chat] ws error', error)
  ws.value.onmessage = event => {
    const data = JSON.parse(event.data)
    if (data.type === 'unread_count') unreadCount.value = data.count
    else if (data.type === 'message') {
      totalCount.value += messages.value.some(item => item.id === data.id) ? 0 : 1
      if (historicalDate.value) newMessageCount.value += 1
      else if (!messages.value.some(item => item.id === data.id)) { messages.value.push(data); scrollToBottom() }
      if (data.sender_id !== store.user.id) unreadCount.value = 0
    }
  }
  ws.value.onclose = () => setTimeout(() => { if (store.isLoggedIn) connectWs() }, 3000)
}

const send = () => {
  const text = inputText.value.trim()
  if (!text) return
  if (historicalDate.value) { ElMessage.info('请先回到最新消息再发送'); return }
  if (!ws.value || ws.value.readyState !== WebSocket.OPEN) { ElMessage.warning('聊天连接尚未就绪，请稍候'); return }
  ws.value.send(JSON.stringify({ content: text, msg_type: 'text' }))
  inputText.value = ''
}
const handleImage = async file => {
  if (historicalDate.value) { ElMessage.info('请先回到最新消息再发送'); return false }
  if (file.size > 10 * 1024 * 1024) { ElMessage.warning('图片不能超过 10MB'); return false }
  try {
    const result = await chatApi.upload(file)
    if (result.message && !messages.value.some(item => item.id === result.message.id)) {
      messages.value.push(result.message); totalCount.value += 1
    }
    scrollToBottom()
  } catch (error) { ElMessage.error(error?.response?.data?.detail || '图片上传失败') }
  return false
}

onMounted(async () => { await Promise.all([loadHistory(), loadPartner()]); connectWs() })
onUnmounted(() => { if (ws.value) { ws.value.onclose = null; ws.value.close() } })
</script>

<style scoped>
.chat-page{position:relative;display:flex;flex-direction:column;flex:1;min-width:0;min-height:0;height:100%;width:100%;max-width:720px;margin:0 auto;overflow:hidden;background:#f2f0ed}
.chat-header,.history-mode-bar,.chat-input{flex-shrink:0}
.chat-messages{min-height:0;overscroll-behavior-y:contain;overflow-anchor:none}
.chat-input .input{min-width:0}
.chat-header{height:64px;padding:0 18px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(60,50,45,.08);background:rgba(255,253,249,.96);backdrop-filter:blur(12px);z-index:3}
.partner-title strong,.partner-title span{display:block}.partner-title strong{color:#282522;font-size:16px}.partner-title span{margin-top:3px;color:#938b84;font-size:9px;letter-spacing:.5px}.partner-title i{display:inline-block;width:5px;height:5px;margin-right:5px;border-radius:50%;background:#7e9c83}
.header-actions{position:relative;display:flex;align-items:center}.date-picker{position:absolute!important;right:0;width:38px!important;opacity:0;pointer-events:none}.calendar-button{width:36px;height:36px;border:0;border-radius:11px;color:#625b55;background:#f1ece7;font-size:17px;cursor:pointer}.badge{margin-left:4px}
.history-mode-bar{padding:8px 16px;display:flex;justify-content:space-between;align-items:center;color:#7b635e;background:#f7e9e5;font-size:10px}.history-mode-bar button{border:0;color:#ad5e5c;background:none;font-size:10px;cursor:pointer}
.chat-messages{flex:1;overflow-y:auto;padding:12px 15px 24px;background:#f2f0ed;display:flex;flex-direction:column;gap:3px}.empty-tip{margin:auto;color:#9a928b;font-size:13px}.history-status{min-height:34px;display:grid;place-items:center;color:#aaa19a;font-size:10px}.history-status button{border:0;color:#847a72;background:rgba(255,255,255,.55);border-radius:999px;padding:7px 13px;font-size:10px;cursor:pointer}
.message-unit{width:100%;align-self:stretch;display:flex;flex-direction:column}.time-divider{width:100%;margin:13px 0 10px;text-align:center}.time-divider span{display:inline-block;padding:3px 6px;border-radius:3px;color:#fff;background:rgba(155,153,151,.48);font-size:10px;line-height:1.35}
.msg-row{display:flex;align-items:flex-start;gap:9px;margin:2px 0 7px}.msg-row.mine{flex-direction:row-reverse}.chat-avatar{flex:0 0 38px;border:2px solid rgba(255,255,255,.75);color:#ad6461;background:#f8e7e3;font-size:13px}.message-content{max-width:72%;display:flex}.mine .message-content{justify-content:flex-end}.bubble{position:relative;padding:9px 12px;border-radius:4px 13px 13px 13px;color:#302c29;background:#fffdf9;font-size:14px;line-height:1.55;word-break:break-word;box-shadow:0 2px 7px rgba(60,50,45,.055)}.bubble::before{content:'';position:absolute;left:-6px;top:10px;border-width:5px 7px 5px 0;border-style:solid;border-color:transparent #fffdf9 transparent transparent}.bubble.mine{border-radius:13px 4px 13px 13px;color:#fff;background:#bd6c68}.bubble.mine::before{left:auto;right:-6px;border-width:5px 0 5px 7px;border-color:transparent transparent transparent #bd6c68}.msg-img{display:block;max-width:220px;max-height:300px;border-radius:7px;object-fit:cover}
.back-latest{position:absolute;right:16px;bottom:70px;z-index:4;padding:8px 11px;display:flex;align-items:center;gap:5px;border:1px solid #e5dbd3;border-radius:999px;color:#9f5e5b;background:#fffdf9;box-shadow:0 5px 18px rgba(50,40,35,.13);font-size:10px;cursor:pointer}
.chat-input{min-height:58px;padding:8px 12px;display:flex;align-items:center;gap:8px;border-top:1px solid rgba(60,50,45,.09);background:#fffdf9}.input-tool{width:35px;height:35px;display:grid;place-items:center;border:0;border-radius:10px;color:#6f6761;background:#f1ede8;font-size:18px;cursor:pointer}.input{flex:1}.input :deep(.el-input__wrapper){border-radius:12px;background:#f5f2ee;box-shadow:none}.chat-input :deep(.el-button--primary){border-color:#bd6c68;border-radius:11px;background:#bd6c68}
@media(max-width:480px){.chat-header{height:58px}.chat-messages{padding-left:11px;padding-right:11px}.message-content{max-width:75%}.msg-img{max-width:min(190px, 100%)}}
</style>
