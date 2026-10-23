<template>
  <div class="page-container rem-page">
    <!-- 标题 -->
    <div class="page-header">
      <div class="title-wrap">
        <h2 class="page-title">智能提醒</h2>
        <p class="page-sub">AI 用心记录，每一个重要时刻</p>
      </div>
      <div class="header-action">
        <el-button text @click="loadReminders" :loading="loading">
          <el-icon :size="14" :class="{ spin: loading }"><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
      </div>
      <div class="deco-line"></div>
    </div>

    <!-- 快速统计 -->
    <div v-if="reminders.length > 0" class="stat-cards">
      <div
        class="stat-card"
        :style="{ '--c': urgentColor, '--bg': urgentBg }"
        @click="filter = 'urgent'"
        :class="{ active: filter === 'urgent' }"
      >
        <div class="sc-num">{{ urgentCount }}</div>
        <div class="sc-label">紧急 (≤3天)</div>
      </div>
      <div
        class="stat-card"
        :style="{ '--c': warnColor, '--bg': warnBg }"
        @click="filter = 'warn'"
        :class="{ active: filter === 'warn' }"
      >
        <div class="sc-num">{{ warnCount }}</div>
        <div class="sc-label">临近 (≤7天)</div>
      </div>
      <div
        class="stat-card"
        :style="{ '--c': infoColor, '--bg': infoBg }"
        @click="filter = 'normal'"
        :class="{ active: filter === 'normal' }"
      >
        <div class="sc-num">{{ normalCount }}</div>
        <div class="sc-label">待办</div>
      </div>
      <div
        class="stat-card"
        :style="{ '--c': allColor, '--bg': allBg }"
        @click="filter = 'all'"
        :class="{ active: filter === 'all' }"
      >
        <div class="sc-num">{{ reminders.length }}</div>
        <div class="sc-label">全部</div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && filtered.length === 0" class="empty-wrap">
      <div class="empty-card ink-card">
        <div class="empty-emoji">
          <svg viewBox="0 0 100 100" width="72" height="72">
            <defs>
              <linearGradient id="bellg" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#c9a96e" stop-opacity="0.3" />
                <stop offset="100%" stop-color="#c96b6b" stop-opacity="0.2" />
              </linearGradient>
            </defs>
            <circle cx="50" cy="52" r="36" fill="url(#bellg)" />
          </svg>
          <el-icon :size="34" color="#c9a96e" class="empty-icon"><Bell /></el-icon>
        </div>
        <div v-if="filter !== 'all' && reminders.length > 0" class="empty-tip">
          暂无「{{ filterLabel(filter) }}」类提醒
          <el-button link type="primary" @click="filter = 'all'">查看全部</el-button>
        </div>
        <div v-else class="empty-tip">
          暂时还没有提醒哦～<br/>
          去设置一些纪念日或添加任务吧 ♥
        </div>
        <el-button type="primary" plain class="empty-btn" @click="goAnniversary">
          <el-icon><Calendar /></el-icon>
          <span>去添加纪念日</span>
        </el-button>
      </div>
    </div>

    <!-- 提醒列表 -->
    <div class="reminder-list" v-if="filtered.length > 0">
      <div class="list-head">
        <span class="list-title">{{ filterLabel(filter) }}提醒 · {{ filtered.length }} 条</span>
        <span class="sort-tip">按时间排序</span>
      </div>

      <transition-group name="rem" tag="div">
        <div
          v-for="r in filtered"
          :key="r.id"
          class="ink-card reminder-card"
          :class="['lv-' + level(r.days_until)]"
          @click="openDetail(r)"
        >
          <div class="card-accent"></div>
          <div class="rc-left">
            <div class="rc-icon" :class="['lv-' + level(r.days_until)]">
              <el-icon :size="20"><component :is="iconOf(r)" /></el-icon>
            </div>
          </div>

          <div class="rc-body">
            <div class="rc-top">
              <div class="rc-type" :class="['lv-' + level(r.days_until)]">
                {{ typeLabel(r.reminder_type) }}
              </div>
              <div class="rc-days" :class="['lv-' + level(r.days_until)]">
                <span v-if="r.days_until === 0" class="today-label">就是今天！</span>
                <span v-else>{{ r.days_until }} 天后</span>
              </div>
            </div>
            <div class="rc-content">{{ r.content }}</div>
            <div class="rc-bottom">
              <span class="rc-date">
                <el-icon :size="11"><Calendar /></el-icon>
                {{ formatDate(r.trigger_date) }}
              </span>
              <span v-if="r.days_until <= 30 && r.days_until > 0" class="rc-countdown">
                {{ countdownText(r.days_until) }}
              </span>
            </div>
          </div>

          <div class="rc-right">
            <el-icon class="rc-arrow" :size="16"><ArrowRight /></el-icon>
          </div>
        </div>
      </transition-group>
    </div>

    <!-- 详情弹窗 -->
    <el-dialog v-model="showDetail" width="88%" top="10vh" class="detail-dialog">
      <div v-if="currentReminder" class="detail-hero" :class="['lv-' + level(currentReminder.days_until)]">
        <div class="detail-icon">
          <el-icon :size="36"><component :is="iconOf(currentReminder)" /></el-icon>
        </div>
        <div class="detail-type">{{ typeLabel(currentReminder.reminder_type) }}</div>
        <div class="detail-countdown" :class="['lv-' + level(currentReminder.days_until)]">
          <div v-if="currentReminder.days_until === 0" class="cd-big">就是今天！</div>
          <template v-else>
            <div class="cd-num">{{ currentReminder.days_until }}</div>
            <div class="cd-unit">天后</div>
          </template>
        </div>
      </div>
      <div v-if="currentReminder" class="detail-body">
        <div class="detail-label">提醒内容</div>
        <div class="detail-content">{{ currentReminder.content }}</div>

        <div class="detail-info">
          <div class="di-row">
            <el-icon :size="14"><Calendar /></el-icon>
            <span class="di-k">日期</span>
            <span class="di-v">{{ formatDate(currentReminder.trigger_date) }}（{{ weekdayLabel(currentReminder.trigger_date) }}）</span>
          </div>
          <div class="di-row">
            <el-icon :size="14"><Timer /></el-icon>
            <span class="di-k">倒计时</span>
            <span class="di-v">还剩 {{ currentReminder.days_until }} 天</span>
          </div>
          <div v-if="currentReminder.is_sent" class="di-row sent">
            <el-icon :size="14" color="#5e8b7e"><CircleCheck /></el-icon>
            <span class="di-k">状态</span>
            <span class="di-v" style="color:var(--accent-teal)">已发送提醒</span>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showDetail = false">关闭</el-button>
        <el-button
          type="rose"
          :disabled="!canShare(currentReminder)"
          @click="shareReminder(currentReminder)"
        >
          <el-icon><Share /></el-icon>
          <span>分享给 TA</span>
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Bell, Calendar, Refresh, ArrowRight, Timer, CircleCheck, Share,
  Present, House, Star, List,
} from '@element-plus/icons-vue'
import { aiApi } from '../../api'

const router = useRouter()

const urgentColor = '#c96b6b'
const urgentBg = '#faf0f0'
const warnColor = '#c9a96e'
const warnBg = '#f7f2e9'
const infoColor = '#5e8b7e'
const infoBg = '#eef5f2'
const allColor = '#6b6b6b'
const allBg = '#f0ede8'

const reminders = ref([])
const loading = ref(false)
const filter = ref('all')
const showDetail = ref(false)
const currentReminder = ref(null)

const urgentCount = computed(() => reminders.value.filter(r => r.days_until <= 3).length)
const warnCount = computed(() => reminders.value.filter(r => r.days_until > 3 && r.days_until <= 7).length)
const normalCount = computed(() => reminders.value.filter(r => r.days_until > 7).length)

const filtered = computed(() => {
  const list = [...reminders.value]
  list.sort((a, b) => a.days_until - b.days_until)
  if (filter.value === 'urgent') return list.filter(r => r.days_until <= 3)
  if (filter.value === 'warn') return list.filter(r => r.days_until > 3 && r.days_until <= 7)
  if (filter.value === 'normal') return list.filter(r => r.days_until > 7)
  return list
})

const level = (d) => {
  if (d === 0) return 'today'
  if (d <= 3) return 'urgent'
  if (d <= 7) return 'warn'
  return 'normal'
}

const typeLabel = (t) => ({
  anniversary: '纪念日',
  birthday: '生日',
  task: '待办',
  custom: '自定义',
  reminder: '提醒',
}[t] || '贴心提醒')

const filterLabel = (f) => ({
  all: '全部',
  urgent: '紧急',
  warn: '临近',
  normal: '待办',
}[f] || '全部')

const iconOf = (r) => {
  const t = r.reminder_type || ''
  if (t.includes('anniv') || t === 'anniversary') return Present
  if (t.includes('birthday')) return Star
  if (t.includes('task') || t === 'reminder') return List
  return Bell
}

const formatDate = (iso) => {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`
}

const weekdayLabel = (iso) => {
  if (!iso) return ''
  const w = new Date(iso).getDay()
  return ['星期日','星期一','星期二','星期三','星期四','星期五','星期六'][w]
}

const countdownText = (d) => {
  if (d <= 1) return '就在明天，记得准备惊喜哦~'
  if (d <= 3) return `还有 ${d} 天，抓紧准备~`
  if (d <= 7) return `还有 ${d} 天，慢慢策划吧`
  if (d <= 30) return `还有 ${d} 天，先记下来`
  return `${d} 天后`
}

const loadReminders = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    reminders.value = await aiApi.reminders()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    if (!silent) ElMessage.error(detail || '加载提醒失败')
  } finally {
    loading.value = false
  }
}

const openDetail = (r) => {
  currentReminder.value = r
  showDetail.value = true
}

const goAnniversary = () => {
  router.push('/anniversary')
}

const canShare = (r) => !!r?.content

const shareReminder = async (r) => {
  const text = `【${typeLabel(r.reminder_type)}】\n${r.content}\n\n日期：${formatDate(r.trigger_date)}（${weekdayLabel(r.trigger_date)}）\n倒计时：${r.days_until === 0 ? '就是今天！' : r.days_until + ' 天后'}`
  if (navigator.share) {
    try {
      await navigator.share({ title: `墨韵 · ${typeLabel(r.reminder_type)}提醒`, text })
      ElMessage.success('分享成功 ♥')
      return
    } catch {}
  }
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('内容已复制，快去粘贴发给 TA 吧 ♥')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

onMounted(() => loadReminders())
</script>

<style scoped>
.rem-page {
  padding-bottom: 40px;
}
.page-header {
  padding: 8px 4px 18px;
  position: relative;
}
.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--ink-darkest);
  margin: 0;
  letter-spacing: 1px;
}
.page-sub {
  font-size: 13px;
  color: var(--ink-light);
  margin-top: 6px;
  letter-spacing: 0.5px;
}
.header-action {
  position: absolute;
  top: 10px;
  right: 0;
  z-index: 2;
}
.header-action .el-button {
  font-size: 12px;
  color: var(--ink-secondary);
  padding: 6px 10px;
}
.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.deco-line {
  position: absolute;
  left: 0;
  bottom: 8px;
  width: 48px;
  height: 3px;
  background: linear-gradient(90deg, var(--accent-rose), var(--accent-teal));
  border-radius: 2px;
}

/* 统计卡片 */
.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 22px;
}
.stat-card {
  background: var(--bg-card);
  border-radius: var(--radius-sm);
  padding: 14px 8px;
  text-align: center;
  cursor: pointer;
  border: 2px solid transparent;
  box-shadow: var(--shadow-soft);
  transition: all 0.25s;
}
.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}
.stat-card.active {
  border-color: var(--c);
  background: var(--bg);
}
.sc-num {
  font-size: 24px;
  font-weight: 700;
  color: var(--c);
  font-family: 'Georgia', serif;
  line-height: 1.1;
}
.sc-label {
  font-size: 11px;
  color: var(--ink-secondary);
  margin-top: 4px;
}
.stat-card.active .sc-label {
  color: var(--c);
  font-weight: 600;
}

/* 空状态 */
.empty-wrap {
  margin-top: 30px;
}
.empty-card {
  padding: 36px 24px;
  text-align: center;
}
.empty-emoji {
  position: relative;
  width: 90px;
  height: 90px;
  margin: 0 auto 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.empty-icon {
  position: absolute;
}
.empty-tip {
  font-size: 14px;
  color: var(--ink-secondary);
  line-height: 1.7;
  margin-bottom: 18px;
}
.empty-btn {
  margin-top: 8px;
  border-radius: var(--radius-sm);
}

/* 列表头部 */
.reminder-list {
  margin-top: 4px;
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px 12px;
}
.list-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-secondary);
}
.sort-tip {
  font-size: 11px;
  color: var(--ink-light);
}

/* 提醒卡片 */
.reminder-card {
  margin-bottom: 12px;
  padding: 16px 18px 16px 20px;
  position: relative;
  display: flex;
  align-items: stretch;
  gap: 14px;
  cursor: pointer;
  transition: all 0.25s;
  overflow: hidden;
}
.reminder-card:hover {
  transform: translateX(3px);
  box-shadow: var(--shadow-hover);
}
.card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: var(--accent-gold);
}
.reminder-card.lv-today .card-accent { background: var(--accent-rose); }
.reminder-card.lv-urgent .card-accent { background: #e48a8a; }
.reminder-card.lv-warn .card-accent { background: #d4b78a; }
.reminder-card.lv-normal .card-accent { background: var(--accent-teal); }

.rc-left {
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
}
.rc-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--bg-soft);
  color: var(--ink-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.25s;
}
.rc-icon.lv-today { background: var(--accent-rose-bg); color: var(--accent-rose); }
.rc-icon.lv-urgent { background: #fcf1f1; color: #e48a8a; }
.rc-icon.lv-warn { background: var(--warnBg); color: var(--warnColor); }
.rc-icon.lv-normal { background: var(--infoBg); color: var(--infoColor); }

.rc-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
}
.rc-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.rc-type {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 100px;
  background: var(--bg-soft);
  color: var(--ink-secondary);
}
.rc-type.lv-today { background: var(--accent-rose-bg); color: var(--accent-rose); }
.rc-type.lv-urgent { background: #fcf1f1; color: #e48a8a; }
.rc-type.lv-warn { background: #f7f2e9; color: #c9a96e; }
.rc-type.lv-normal { background: var(--infoBg); color: var(--infoColor); }

.rc-days {
  font-size: 13px;
  font-weight: 700;
  font-family: 'Georgia', serif;
  color: var(--ink-secondary);
  flex-shrink: 0;
}
.rc-days.lv-today { color: var(--accent-rose); }
.rc-days.lv-urgent { color: #e48a8a; }
.rc-days.lv-warn { color: #c9a96e; }
.rc-days.lv-normal { color: var(--infoColor); }
.today-label {
  display: inline-block;
  padding: 3px 10px;
  background: var(--accent-rose);
  color: #fff !important;
  border-radius: 100px;
  font-size: 11px;
  font-weight: 600;
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(201,107,107,0.3); }
  50% { transform: scale(1.05); box-shadow: 0 0 0 8px rgba(201,107,107,0); }
}

.rc-content {
  font-size: 15px;
  line-height: 1.55;
  color: var(--ink-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.rc-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px;
}
.rc-date {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--ink-light);
}
.rc-countdown {
  font-size: 11px;
  color: var(--accent-gold);
}
.rc-right {
  display: flex;
  align-items: center;
  padding-left: 4px;
}
.rc-arrow {
  color: var(--ink-light);
}

/* 列表过渡动画 */
.rem-enter-active, .rem-leave-active {
  transition: all 0.3s ease;
}
.rem-enter-from { opacity: 0; transform: translateX(-10px); }
.rem-leave-to { opacity: 0; transform: translateX(10px); }
.rem-move { transition: transform 0.3s ease; }

/* 详情弹窗 */
.detail-dialog :deep(.el-dialog) {
  border-radius: 20px;
  overflow: hidden;
  padding: 0;
}
.detail-hero {
  padding: 28px 24px 24px;
  text-align: center;
  background: linear-gradient(180deg, #f7f5f0 0%, #ffffff 100%);
}
.detail-hero.lv-today {
  background: linear-gradient(180deg, #faf0f0 0%, #ffffff 100%);
}
.detail-hero.lv-urgent {
  background: linear-gradient(180deg, #fcf4f4 0%, #ffffff 100%);
}
.detail-hero.lv-warn {
  background: linear-gradient(180deg, #faf6ee 0%, #ffffff 100%);
}
.detail-icon {
  width: 72px;
  height: 72px;
  margin: 0 auto 14px;
  border-radius: 20px;
  background: var(--bg-card);
  color: var(--ink-secondary);
  box-shadow: var(--shadow-soft);
  display: flex;
  align-items: center;
  justify-content: center;
}
.detail-hero.lv-today .detail-icon { background: var(--accent-rose-bg); color: var(--accent-rose); }
.detail-hero.lv-urgent .detail-icon { background: #fcf1f1; color: #e48a8a; }
.detail-hero.lv-warn .detail-icon { background: #f7f2e9; color: var(--warnColor); }
.detail-hero.lv-normal .detail-icon { background: var(--infoBg); color: var(--infoColor); }

.detail-type {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-secondary);
  margin-bottom: 12px;
}
.detail-countdown {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}
.detail-countdown.lv-today .cd-big {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent-rose);
}
.detail-countdown .cd-num {
  font-size: 40px;
  font-weight: 700;
  color: var(--ink-darkest);
  font-family: 'Georgia', serif;
  line-height: 1;
}
.detail-countdown.lv-today .cd-num { color: var(--accent-rose); }
.detail-countdown.lv-urgent .cd-num { color: #e48a8a; }
.detail-countdown.lv-warn .cd-num { color: var(--warnColor); }
.detail-countdown.lv-normal .cd-num { color: var(--infoColor); }
.detail-countdown .cd-unit {
  font-size: 14px;
  color: var(--ink-secondary);
  font-weight: 500;
}
.detail-body {
  padding: 20px 24px;
}
.detail-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-light);
  margin-bottom: 8px;
}
.detail-content {
  font-size: 16px;
  line-height: 1.8;
  color: var(--ink-primary);
  padding: 14px 16px;
  background: var(--bg-paper);
  border-radius: var(--radius-sm);
  margin-bottom: 20px;
}
.detail-info {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
}
.di-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--ink-primary);
}
.di-row :deep(svg) {
  color: var(--ink-light);
}
.di-k {
  color: var(--ink-light);
  min-width: 48px;
}
.di-v {
  flex: 1;
  font-weight: 500;
}

@media (max-width: 480px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .rc-content {
    -webkit-line-clamp: 3;
  }
}
</style>
