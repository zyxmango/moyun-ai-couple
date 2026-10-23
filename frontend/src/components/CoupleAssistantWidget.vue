<template>
  <div
    class="assistant-widget"
    :class="{ 'align-left': alignLeft, dragging: dragging }"
    :style="widgetStyle"
  >
    <transition name="assistant-pop">
      <aside v-if="greetingVisible && !panelOpen" class="reminder-teaser greeting-teaser" role="status">
        <span class="teaser-heart">♥</span>
        <button class="greeting-content" type="button" @click="openPanel"><b>小忆 · 你们的情侣助手</b>{{ greetingText }}</button>
        <button class="greeting-close" type="button" aria-label="关闭欢迎语" @click="dismissGreeting"><el-icon><Close /></el-icon></button>
      </aside>
    </transition>
    <transition name="assistant-pop">
      <button
        v-if="teaserVisible && importantReminders.length && !panelOpen && !greetingVisible"
        class="reminder-teaser"
        type="button"
        @click="openPanel"
      >
        <span class="teaser-heart">♥</span>
        <span><b>小忆提醒你</b>{{ importantReminders[0].content }}</span>
        <span class="teaser-arrow">›</span>
      </button>
    </transition>

    <transition name="assistant-panel">
      <section v-if="panelOpen" class="assistant-panel" aria-label="情侣助手聊天窗口">
        <header class="assistant-header">
          <div class="assistant-identity">
            <div class="assistant-avatar"><span class="tiny-couple">♥</span></div>
            <div><strong>小忆</strong><span>你们的情侣助手</span></div>
          </div>
          <div class="header-actions">
            <button type="button" title="新对话" @click="newChat"><el-icon><Refresh /></el-icon></button>
            <button type="button" title="关闭" @click="panelOpen = false"><el-icon><Close /></el-icon></button>
          </div>
        </header>

        <button
          v-if="importantReminders.length"
          class="reminder-strip"
          type="button"
          @click="goToReminders"
        >
          <el-icon><Bell /></el-icon>
          <span>{{ importantReminders[0].content }}</span>
          <small v-if="importantReminders.length > 1">还有 {{ importantReminders.length - 1 }} 条</small>
        </button>

        <div ref="chatBox" class="assistant-messages">
          <div v-if="!messages.length" class="assistant-welcome">
            <div class="welcome-mark">♥</div>
            <h3>嗨，我是小忆</h3>
            <p>我会记住你们的重要时刻，也可以陪你聊聊关于彼此的事。</p>
            <div class="quick-questions">
              <button v-for="item in suggestions" :key="item" type="button" @click="send(item)">{{ item }}</button>
            </div>
          </div>

          <div v-for="message in messages" :key="message.id" class="assistant-message" :class="message.role">
            <div v-if="message.role === 'assistant'" class="mini-avatar">♥</div>
            <div class="message-bubble">{{ message.content }}</div>
          </div>
          <div v-if="loading" class="assistant-message assistant">
            <div class="mini-avatar">♥</div>
            <div class="message-bubble typing"><i></i><i></i><i></i></div>
          </div>
        </div>

        <form class="assistant-input" @submit.prevent="send()">
          <input v-model="input" maxlength="500" placeholder="问问关于你们的事…" />
          <button type="submit" :disabled="!input.trim() || loading" aria-label="发送">
            <el-icon><Promotion /></el-icon>
          </button>
        </form>
      </section>
    </transition>

    <button
      class="assistant-launcher"
      :class="{ active: panelOpen }"
      type="button"
      aria-label="打开情侣助手"
      title="小忆情侣助手（可拖动）"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="endDrag"
      @pointercancel="endDrag"
      @click="handleLauncherClick"
    >
      <svg class="couple-assistant-icon" viewBox="0 0 64 64" aria-hidden="true">
        <circle cx="22" cy="25" r="9" />
        <circle cx="42" cy="25" r="9" />
        <path d="M8 49c1-9 7-14 14-14 5 0 9 3 11 7" />
        <path d="M56 49c-1-9-7-14-14-14-5 0-9 3-11 7" />
        <path class="icon-heart" d="M32 51c-6-4-10-7-10-12 0-6 8-8 10-2 2-6 10-4 10 2 0 5-4 8-10 12z" />
      </svg>
      <span v-if="importantReminders.length && !panelOpen" class="reminder-badge">
        {{ Math.min(importantReminders.length, 9) }}
      </span>
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bell, Close, Promotion, Refresh } from '@element-plus/icons-vue'
import { aiApi } from '../api'
import { useUserStore } from '../stores/user'

const router = useRouter()
const store = useUserStore()
const panelOpen = ref(false)
const greetingVisible = ref(false)
const greetingText = ref('')
let greetingTimer = null
const dismissGreeting = () => {
  greetingVisible.value = false
  clearTimeout(greetingTimer)
}
const showGreeting = () => {
  const userId = store.user?.id
  if (!userId) return
  const sessionKey = `couple-assistant-greeted:${userId}`
  if (!store.assistantGreetingPending && sessionStorage.getItem(sessionKey)) return
  const introKey = `couple-assistant-introduced:${userId}`
  const firstVisit = !localStorage.getItem(introKey)
  const greetings = [
    '欢迎回来！新的一天，和 Ta 一起留点值得记住的小事吧。',
    '欢迎回来，今天也要好好相伴。想回忆往事或安排约会，随时找我。',
    '又见面啦！今天有什么开心的小事，想和 Ta 分享吗？',
  ]
  greetingText.value = firstVisit
    ? '嗨，我是小忆！在墨韵，我陪你们记住日常、规划约会，也提醒重要日子。'
    : greetings[new Date().getDate() % greetings.length]
  localStorage.setItem(introKey, '1')
  sessionStorage.setItem(sessionKey, '1')
  store.assistantGreetingPending = false
  greetingVisible.value = true
  greetingTimer = setTimeout(dismissGreeting, 12000)
}
const teaserVisible = ref(false)
const historyLoaded = ref(false)
const loading = ref(false)
const input = ref('')
const messages = ref([])
const conversationId = ref(null)
const reminders = ref([])
const chatBox = ref(null)
const dragPosition = ref(null)
const dragging = ref(false)
const viewportWidth = ref(720)
const dragState = { pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0, moved: false }
let skipLauncherClick = false
let reminderTimer = null
let teaserTimer = null

const positionKey = computed(() => `couple-assistant-position:${store.user?.id || 'user'}`)
const widgetStyle = computed(() => dragPosition.value ? {
  left: `${dragPosition.value.x}px`,
  top: `${dragPosition.value.y}px`,
  right: 'auto',
  bottom: 'auto',
} : {})
const alignLeft = computed(() => !!dragPosition.value && dragPosition.value.x < viewportWidth.value / 2)

const suggestions = [
  '我们最近有哪些重要安排？',
  '下一个纪念日是什么时候？',
  '帮我想一个适合对方的小惊喜',
]

const importantReminders = computed(() =>
  reminders.value.filter(item => Number(item.days_until) <= 7).slice(0, 5)
)

const scrollToBottom = () => nextTick(() => {
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
})

const reminderSeenKey = (reminder) => {
  const day = new Date().toLocaleDateString('sv-SE')
  return `couple-assistant-reminder:${store.user?.id || 'user'}:${reminder.id}:${day}`
}

const loadReminders = async (allowTeaser = false) => {
  try {
    reminders.value = await aiApi.reminders()
    const first = importantReminders.value[0]
    if (allowTeaser && first && !localStorage.getItem(reminderSeenKey(first))) {
      localStorage.setItem(reminderSeenKey(first), '1')
      clearTimeout(teaserTimer)
      teaserTimer = setTimeout(() => { teaserVisible.value = true }, 1200)
    }
  } catch {
    reminders.value = []
  }
}

const loadLatestConversation = async () => {
  if (historyLoaded.value) return
  historyLoaded.value = true
  try {
    const conversations = await aiApi.companionHistory({})
    if (conversations.length) {
      conversationId.value = conversations[0].id
      messages.value = conversations[0].messages || []
      scrollToBottom()
    }
  } catch {
    // 首次使用时没有历史记录是正常状态。
  }
}

const openPanel = async () => {
  dismissGreeting()
  panelOpen.value = true
  teaserVisible.value = false
  await loadLatestConversation()
}

const togglePanel = () => panelOpen.value ? (panelOpen.value = false) : openPanel()

const clampPosition = (x, y) => ({
  x: Math.min(Math.max(10, x), Math.max(10, window.innerWidth - 64)),
  y: Math.min(
    Math.max(10, y),
    Math.max(10, window.innerHeight - (router.currentRoute.value.path === '/chat' ? 186 : 128)),
  ),
})

const startDrag = (event) => {
  if (event.button !== undefined && event.button !== 0) return
  const rect = event.currentTarget.getBoundingClientRect()
  dragState.pointerId = event.pointerId
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.originX = rect.left
  dragState.originY = rect.top
  dragState.moved = false
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

const moveDrag = (event) => {
  if (dragState.pointerId !== event.pointerId) return
  const dx = event.clientX - dragState.startX
  const dy = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(dx, dy) < 5) return
  dragState.moved = true
  dragging.value = true
  dragPosition.value = clampPosition(dragState.originX + dx, dragState.originY + dy)
  event.preventDefault()
}

const endDrag = (event) => {
  if (dragState.pointerId !== event.pointerId) return
  if (dragState.moved && dragPosition.value) {
    localStorage.setItem(positionKey.value, JSON.stringify(dragPosition.value))
    skipLauncherClick = true
    setTimeout(() => { skipLauncherClick = false }, 0)
  }
  dragging.value = false
  dragState.pointerId = null
}

const handleLauncherClick = () => {
  if (skipLauncherClick) { skipLauncherClick = false; return }
  togglePanel()
}

const restorePosition = () => {
  viewportWidth.value = window.innerWidth
  try {
    const saved = JSON.parse(localStorage.getItem(positionKey.value) || 'null')
    if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      dragPosition.value = clampPosition(saved.x, saved.y)
    }
  } catch { localStorage.removeItem(positionKey.value) }
}

const keepPositionVisible = () => {
  viewportWidth.value = window.innerWidth
  if (!dragPosition.value) return
  dragPosition.value = clampPosition(dragPosition.value.x, dragPosition.value.y)
  localStorage.setItem(positionKey.value, JSON.stringify(dragPosition.value))
}

const send = async (quickText) => {
  const content = typeof quickText === 'string' ? quickText : input.value.trim()
  if (!content || loading.value) return
  input.value = ''
  messages.value.push({ id: `local-${Date.now()}`, role: 'user', content })
  loading.value = true
  scrollToBottom()
  try {
    const result = await aiApi.companionChat({
      user_message: content,
      conversation_id: conversationId.value,
    })
    conversationId.value = result.conversation_id
    messages.value.push(result.message)
  } catch {
    messages.value.push({
      id: `error-${Date.now()}`,
      role: 'assistant',
      content: '我刚刚走神了一下，暂时没能回答。等一会儿再问我吧。',
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const newChat = () => {
  messages.value = []
  conversationId.value = null
}

const goToReminders = () => {
  panelOpen.value = false
  router.push('/ai/reminders')
}

onMounted(() => {
  restorePosition()
  showGreeting()
  window.addEventListener('resize', keepPositionVisible)
  loadReminders(true)
  reminderTimer = setInterval(() => loadReminders(false), 5 * 60 * 1000)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', keepPositionVisible)
  clearInterval(reminderTimer)
  clearTimeout(teaserTimer)
  clearTimeout(greetingTimer)
})
</script>

<style scoped>
.assistant-widget {
  position: fixed;
  right: max(18px, calc((100vw - 720px) / 2 + 18px));
  bottom: 74px;
  z-index: 500;
}
.assistant-widget.chat-offset { bottom: 132px; }
.assistant-launcher {
  position: relative;
  width: 54px;
  height: 54px;
  border: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(145deg, #d67a7a, #bd5e67);
  box-shadow: 0 8px 26px rgba(163, 75, 83, .32);
  cursor: pointer;
  touch-action: none;
  user-select: none;
  transition: transform .2s ease, box-shadow .2s ease;
}
.assistant-widget.dragging .assistant-launcher { cursor: grabbing; transform:scale(1.06); box-shadow:0 13px 32px rgba(163,75,83,.42); }
.couple-assistant-icon { width:39px; height:39px; overflow:visible; }
.couple-assistant-icon circle,.couple-assistant-icon>path:not(.icon-heart) { fill:none; stroke:#fff; stroke-width:3.2; stroke-linecap:round; stroke-linejoin:round; }
.couple-assistant-icon .icon-heart { fill:#fff; stroke:#fff; stroke-width:1.5; }
.assistant-launcher:hover { transform: translateY(-2px); box-shadow: 0 11px 30px rgba(163, 75, 83, .38); }
.assistant-launcher.active { transform: rotate(-8deg); }
.reminder-badge {
  position: absolute;
  top: -3px;
  right: -2px;
  min-width: 19px;
  height: 19px;
  padding: 0 5px;
  border: 2px solid #fff;
  border-radius: 10px;
  color: #fff;
  background: var(--ink-dark);
  font-size: 10px;
  line-height: 15px;
}
.reminder-teaser {
  position: absolute;
  right: 0;
  bottom: 66px;
  width: 300px;
  border: 1px solid rgba(201, 107, 107, .18);
  border-radius: 15px;
  padding: 13px 12px;
  display: grid;
  grid-template-columns: 28px 1fr 12px;
  gap: 9px;
  align-items: center;
  text-align: left;
  color: var(--ink-primary);
  background: rgba(255, 255, 255, .97);
  box-shadow: 0 12px 36px rgba(44, 44, 44, .14);
  cursor: pointer;
}
.teaser-heart { width: 28px; height: 28px; border-radius: 50%; display:grid; place-items:center; color:var(--accent-rose); background:var(--accent-rose-bg); }
.reminder-teaser b { display:block; margin-bottom:3px; color:var(--ink-darkest); font-size:12px; }
.reminder-teaser span:nth-child(2) { overflow:hidden; font-size:12px; line-height:1.45; }
.teaser-arrow { color:var(--ink-light); font-size:20px; }
.greeting-teaser{width:min(300px, calc(100vw - 32px));cursor:default}
.greeting-content{padding:0;border:0;background:transparent;color:inherit;font:inherit;font-size:12px;line-height:1.6;text-align:left;cursor:pointer}
.greeting-close{display:grid;place-items:center;align-self:start;width:22px;height:22px;padding:0;border:0;background:transparent;color:var(--ink-light);cursor:pointer}
.assistant-panel {
  position: absolute;
  right: 0;
  bottom: 66px;
  width: 380px;
  height: min(590px, calc(100vh - 160px));
  border: 1px solid rgba(232, 228, 222, .9);
  border-radius: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, .98);
  box-shadow: 0 18px 55px rgba(44, 44, 44, .18);
  backdrop-filter: blur(18px);
}
.assistant-header { padding:14px 15px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--border-soft); background:linear-gradient(135deg,#fff,#faf0f0); }
.assistant-identity { display:flex; align-items:center; gap:10px; }
.assistant-avatar { width:36px; height:36px; border-radius:13px; display:grid; place-items:center; color:#fff; background:linear-gradient(145deg,#d67a7a,#bd5e67); }
.tiny-couple { position:relative; font-size:15px; }.tiny-couple::before,.tiny-couple::after{content:'';position:absolute;top:-5px;width:7px;height:7px;border:1.5px solid #fff;border-radius:50%}.tiny-couple::before{left:-6px}.tiny-couple::after{right:-6px}
.assistant-identity strong,.assistant-identity span { display:block; }
.assistant-identity strong { color:var(--ink-darkest); font-size:14px; }
.assistant-identity span { margin-top:2px; color:var(--ink-light); font-size:10px; }
.header-actions { display:flex; gap:3px; }
.header-actions button { width:30px; height:30px; border:0; border-radius:9px; display:grid; place-items:center; color:var(--ink-secondary); background:transparent; cursor:pointer; }
.header-actions button:hover { background:var(--bg-soft); }
.reminder-strip { margin:10px 12px 0; border:0; border-radius:11px; padding:10px 11px; display:flex; align-items:center; gap:8px; color:#7d5954; background:#fff5ed; text-align:left; cursor:pointer; }
.reminder-strip span { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }
.reminder-strip small { color:#ad827b; font-size:9px; }
.assistant-messages { flex:1; overflow-y:auto; padding:15px 13px; display:flex; flex-direction:column; gap:12px; }
.assistant-welcome { margin:auto 12px; text-align:center; }
.welcome-mark { width:46px; height:46px; margin:0 auto 10px; border-radius:17px; display:grid; place-items:center; color:var(--accent-rose); background:var(--accent-rose-bg); font-size:20px; }
.assistant-welcome h3 { margin:0 0 6px; color:var(--ink-darkest); font-size:16px; }
.assistant-welcome p { margin:0 auto 16px; max-width:270px; color:var(--ink-secondary); font-size:12px; line-height:1.7; }
.quick-questions { display:flex; flex-direction:column; gap:7px; }
.quick-questions button { border:1px solid var(--border-soft); border-radius:10px; padding:9px 11px; color:var(--ink-primary); background:#fff; font-size:11px; cursor:pointer; }
.quick-questions button:hover { border-color:var(--accent-rose-light); background:var(--accent-rose-bg); }
.assistant-message { display:flex; align-items:flex-start; gap:7px; }
.assistant-message.user { justify-content:flex-end; }
.mini-avatar { width:25px; height:25px; flex:0 0 25px; border-radius:9px; display:grid; place-items:center; color:var(--accent-rose); background:var(--accent-rose-bg); font-size:10px; }
.message-bubble { max-width:78%; border-radius:5px 14px 14px 14px; padding:9px 11px; color:var(--ink-primary); background:var(--bg-soft); font-size:12px; line-height:1.65; white-space:pre-wrap; }
.assistant-message.user .message-bubble { border-radius:14px 5px 14px 14px; color:#fff; background:var(--accent-rose); }
.typing { display:flex; align-items:center; gap:4px; min-height:34px; }
.typing i { width:5px; height:5px; border-radius:50%; background:var(--ink-light); animation:typing 1.1s infinite ease-in-out; }
.typing i:nth-child(2) { animation-delay:.15s; }.typing i:nth-child(3) { animation-delay:.3s; }
.assistant-input { padding:10px 11px; display:flex; gap:8px; border-top:1px solid var(--border-soft); background:#fff; }
.assistant-input input { flex:1; min-width:0; border:1px solid var(--border-soft); border-radius:12px; outline:none; padding:10px 12px; color:var(--ink-primary); background:var(--bg-paper); font-size:12px; }
.assistant-input input:focus { border-color:var(--accent-rose-light); background:#fff; }
.assistant-input button { width:38px; height:38px; border:0; border-radius:12px; display:grid; place-items:center; color:#fff; background:var(--ink-dark); cursor:pointer; }
.assistant-input button:disabled { opacity:.35; cursor:not-allowed; }
.assistant-panel-enter-active,.assistant-panel-leave-active { transition:opacity .2s ease,transform .22s ease; transform-origin:bottom right; }
.assistant-widget.align-left .assistant-panel,.assistant-widget.align-left .reminder-teaser { left:0; right:auto; }
.assistant-widget.align-left .assistant-panel-enter-active,.assistant-widget.align-left .assistant-panel-leave-active { transform-origin:bottom left; }
.assistant-panel-enter-from,.assistant-panel-leave-to { opacity:0; transform:translateY(12px) scale(.96); }
.assistant-pop-enter-active,.assistant-pop-leave-active { transition:opacity .25s ease,transform .25s ease; }
.assistant-pop-enter-from,.assistant-pop-leave-to { opacity:0; transform:translateY(8px); }
@keyframes typing { 0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-3px);opacity:1} }
@media (max-width: 520px) {
  .assistant-widget { right:14px; bottom:70px; }
  .assistant-widget.chat-offset { bottom:132px; }
  .assistant-panel { position:fixed; left:10px; right:10px; bottom:72px; width:auto; height:min(70vh,570px); }
  .reminder-teaser { width:min(300px,calc(100vw - 28px)); }
}
</style>
