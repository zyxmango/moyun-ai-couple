<template>
  <div class="page-container sum-page">
    <!-- 标题 -->
    <div class="page-header">
      <div class="title-wrap">
        <h2 class="page-title">AI 日记总结</h2>
        <p class="page-sub">记录情感轨迹，珍藏你们的时光</p>
      </div>
      <div class="deco-line"></div>
    </div>

    <!-- 周期选择 -->
    <div class="period-row">
      <div
        v-for="p in periods"
        :key="p.key"
        class="period-card ink-card"
        :class="{ active: period === p.key }"
        :style="{ '--p-color': p.color, '--p-bg': p.bg }"
        @click="period = p.key"
      >
        <div class="period-icon">
          <el-icon :size="22"><component :is="p.icon" /></el-icon>
        </div>
        <div class="period-info">
          <div class="period-name">{{ p.name }}</div>
          <div class="period-hint">{{ p.hint }}</div>
        </div>
      </div>
    </div>

    <!-- 生成按钮 -->
    <el-button class="sum-btn" type="rose" size="large" :loading="loading" @click="generate">
      <el-icon class="btn-icon"><MagicStick /></el-icon>
      <span>生成情感总结</span>
    </el-button>

    <!-- 当前结果卡片 -->
    <transition name="fade">
      <div v-if="current" class="ink-card result-card">
        <div class="result-head">
          <div class="result-left">
            <div class="emotion-badge" :style="{ background: emotionStyle?.bg, color: emotionStyle?.color }">
              <el-icon :size="14"><component :is="emotionStyle?.icon" /></el-icon>
              <span>{{ emotionStyle?.label }}</span>
            </div>
          </div>
          <div class="result-actions">
            <el-button text size="small" @click="copyResult">
              <el-icon><DocumentCopy /></el-icon>复制
            </el-button>
            <el-button text size="small" @click="shareResult">
              <el-icon><Share /></el-icon>分享
            </el-button>
          </div>
        </div>

        <h3 class="result-title">{{ current.title || '情感总结报告' }}</h3>

        <div class="stat-row">
          <div class="stat-item">
            <div class="stat-num">{{ current.diary_count || '-' }}</div>
            <div class="stat-label">篇日记</div>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <div class="stat-num">{{ period === 'daily' ? '日' : '周' }}</div>
            <div class="stat-label">总结周期</div>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <div class="stat-num date">{{ current.date ? current.date.split(' ')[0] : '-' }}</div>
            <div class="stat-label">日期</div>
          </div>
        </div>

        <div class="result-divider"></div>

        <div class="result-body">
          <div class="result-text">{{ current.content }}</div>
        </div>

        <!-- 情感关键词 -->
        <div v-if="keywords.length > 0" class="kw-block">
          <div class="kw-label">情感关键词</div>
          <div class="kw-tags">
            <span v-for="(k, i) in keywords" :key="i" class="kw-tag" :style="{ '--i': i }">{{ k }}</span>
          </div>
        </div>
      </div>
    </transition>

    <!-- 历史时间线 -->
    <div v-if="history.length > 0" class="timeline-block">
      <div class="block-title">
        <span class="dot"></span>
        <span>历史总结</span>
        <span class="count">{{ history.length }} 篇</span>
      </div>
      <div class="timeline">
        <div
          v-for="(h, idx) in history"
          :key="h.id"
          class="timeline-item"
          :class="{ active: idx === 0 }"
          @click="showHistory(h)"
        >
          <div class="timeline-dot"></div>
          <div class="timeline-line" v-if="idx < history.length - 1"></div>
          <div class="ink-card timeline-card">
            <div class="tl-head">
              <div class="tl-title">{{ h.title || '情感总结' }}</div>
              <div class="tl-arrow">›</div>
            </div>
            <div class="tl-preview">{{ (h.content || '').slice(0, 50) }}{{ (h.content || '').length > 50 ? '...' : '' }}</div>
            <div class="tl-meta">
              <span class="tl-time">
                <el-icon :size="11"><Clock /></el-icon>
                {{ formatTime(h.created_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Sunny, Calendar, MagicStick, DocumentCopy, Share, Clock,
} from '@element-plus/icons-vue'
import { aiApi } from '../../api'

const periods = [
  {
    key: 'daily',
    name: '每日总结',
    hint: '回顾今日点滴',
    icon: Sunny,
    color: '#c9a96e',
    bg: '#f7f2e9',
  },
  {
    key: 'weekly',
    name: '每周总结',
    hint: '细数一周温情',
    icon: Calendar,
    color: '#5e8b7e',
    bg: '#eef5f2',
  },
]

const period = ref('daily')
const loading = ref(false)
const current = ref(null)
const history = ref([])

const emotionEmojis = ['🌅', '💕', '☁️', '🌸', '🌙', '✨', '🍃']

const emotionStyle = computed(() => {
  const c = (current.value?.content || '') + (current.value?.title || '')
  const positive = /(开心|快乐|幸福|甜蜜|浪漫|感动|美好|惊喜|温馨|期待|满足|温暖|爱|喜欢|愉悦|愉快)/g
  const sad = /(难过|伤心|失落|不安|焦虑|担心|想念|思念|孤独|委屈|疲惫|累)/g
  const p = (c.match(positive) || []).length
  const s = (c.match(sad) || []).length
  if (p > s) return { label: '甜蜜幸福', icon: Sunny, color: '#c96b6b', bg: '#faf0f0' }
  if (s > p) return { label: '思念绵绵', icon: Calendar, color: '#7b8ac2', bg: '#eef0f7' }
  return { label: '温柔日常', icon: Calendar, color: '#c9a96e', bg: '#f7f2e9' }
})

const keywords = computed(() => {
  const c = current.value?.content || ''
  const kw = []
  const patterns = [
    /「([^」]{1,6})」/g,
    /【([^】]{1,6})】/g,
    /《([^》]{1,6})》/g,
  ]
  for (const p of patterns) {
    let m
    while ((m = p.exec(c)) && kw.length < 6) {
      if (!kw.includes(m[1])) kw.push(m[1])
    }
  }
  if (kw.length < 3) {
    const words = (c.match(/[\u4e00-\u9fa5]{2,4}/g) || []).slice(0, 6 - kw.length)
    for (const w of words) {
      if (!kw.includes(w)) kw.push(w)
    }
  }
  return kw.slice(0, 6)
})

const formatTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const y = d.getFullYear() === now.getFullYear()
    ? ''
    : `${d.getFullYear()}年`
  return `${y}${d.getMonth() + 1}月${d.getDate()}日 ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

const generate = async () => {
  loading.value = true
  try {
    current.value = await aiApi.summary({ period: period.value })
    if (current.value) {
      current.value.date = new Date().toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      })
    }
    loadHistory()
    setTimeout(() => {
      document.querySelector('.result-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 100)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '生成总结失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const showHistory = (h) => {
  current.value = {
    title: h.title,
    content: h.content,
    date: formatTime(h.created_at),
    diary_count: '-',
  }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const loadHistory = async () => {
  try {
    history.value = await aiApi.summaryList()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载历史总结失败')
  }
}

const copyResult = () => {
  if (!current.value?.content) return
  const text = `${current.value.title || '情感总结'}\n\n${current.value.content}`
  navigator.clipboard.writeText(text)
    .then(() => ElMessage.success('已复制 ♥'))
    .catch(() => ElMessage.warning('复制失败，请手动复制'))
}

const shareResult = async () => {
  if (!current.value?.content) return
  const text = `${current.value.title || '情感总结'}\n\n${current.value.content}`
  if (navigator.share) {
    try {
      await navigator.share({ title: current.value.title || '情感总结', text })
      ElMessage.success('分享成功')
      return
    } catch {}
  }
  copyResult()
  ElMessage.success('内容已复制，可粘贴分享给 TA ♥')
}

onMounted(loadHistory)
</script>

<style scoped>
.sum-page {
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
.deco-line {
  position: absolute;
  left: 0;
  bottom: 8px;
  width: 48px;
  height: 3px;
  background: linear-gradient(90deg, var(--accent-teal), var(--accent-gold));
  border-radius: 2px;
}

/* 周期选择 */
.period-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.period-card {
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.25s ease;
}
.period-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}
.period-card.active {
  border-color: var(--p-color);
  background: var(--p-bg);
}
.period-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--p-bg);
  color: var(--p-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.period-card.active .period-icon {
  background: var(--p-color);
  color: #fff;
}
.period-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.period-hint {
  font-size: 12px;
  color: var(--ink-light);
  margin-top: 2px;
}

/* 生成按钮 */
.sum-btn {
  width: 100%;
  height: 46px;
  margin-bottom: 20px;
  font-size: 15px;
  border-radius: var(--radius-md);
}
.btn-icon {
  margin-right: 6px;
}

/* 结果卡片 */
.result-card {
  margin-bottom: 20px;
  background: linear-gradient(180deg, #fafbf8 0%, #ffffff 100%);
  border: 1px solid var(--border-soft);
  animation: slideIn 0.4s ease;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.emotion-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 100px;
  font-size: 12px;
  font-weight: 600;
}
.result-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--ink-darkest);
  margin: 0 0 16px;
  letter-spacing: 0.5px;
}
.stat-row {
  display: flex;
  align-items: stretch;
  background: var(--bg-soft);
  border-radius: var(--radius-sm);
  padding: 14px 8px;
  margin-bottom: 16px;
}
.stat-item {
  flex: 1;
  text-align: center;
}
.stat-num {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink-darkest);
  font-family: 'Georgia', serif;
}
.stat-num.date {
  font-size: 15px;
}
.stat-label {
  font-size: 11px;
  color: var(--ink-light);
  margin-top: 4px;
}
.stat-divider {
  width: 1px;
  background: var(--border-soft);
  margin: 4px 0;
}
.result-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-soft), transparent);
  margin: 6px 0 14px;
}
.result-body {
  padding: 4px 4px 12px;
}
.result-text {
  font-size: 15px;
  line-height: 2;
  color: var(--ink-primary);
  white-space: pre-wrap;
  letter-spacing: 0.3px;
}

/* 情感关键词 */
.kw-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--border-soft);
}
.kw-label {
  font-size: 12px;
  color: var(--ink-secondary);
  margin-bottom: 10px;
  font-weight: 600;
}
.kw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.kw-tag {
  padding: 6px 14px;
  background: linear-gradient(135deg, #faf0f0 0%, #f7f2e9 100%);
  border-radius: 100px;
  font-size: 12px;
  color: var(--ink-primary);
  animation: fadeInTag 0.4s ease both;
  animation-delay: calc(var(--i) * 0.08s);
}
@keyframes fadeInTag {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 时间线 */
.timeline-block {
  margin-top: 24px;
}
.block-title {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-secondary);
}
.block-title .dot {
  width: 4px;
  height: 16px;
  background: linear-gradient(180deg, var(--accent-teal), var(--accent-gold));
  border-radius: 2px;
}
.block-title .count {
  margin-left: auto;
  font-size: 11px;
  font-weight: 400;
  color: var(--ink-light);
}
.timeline {
  position: relative;
  padding-left: 8px;
}
.timeline-item {
  position: relative;
  padding-left: 24px;
  margin-bottom: 14px;
  cursor: pointer;
}
.timeline-dot {
  position: absolute;
  left: 0;
  top: 20px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--border-soft);
  border: 2px solid var(--bg-paper);
  box-shadow: 0 0 0 2px var(--border-soft);
  z-index: 1;
  transition: all 0.25s;
}
.timeline-item.active .timeline-dot,
.timeline-item:hover .timeline-dot {
  background: var(--accent-teal);
  box-shadow: 0 0 0 2px var(--accent-teal);
}
.timeline-line {
  position: absolute;
  left: 5px;
  top: 34px;
  width: 2px;
  bottom: -14px;
  background: var(--border-soft);
}
.timeline-card {
  padding: 14px 16px;
  transition: all 0.2s;
}
.timeline-card:hover {
  transform: translateX(4px);
  box-shadow: var(--shadow-hover);
}
.tl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.tl-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.tl-arrow {
  font-size: 18px;
  color: var(--ink-light);
}
.tl-preview {
  font-size: 13px;
  color: var(--ink-secondary);
  line-height: 1.6;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tl-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.tl-time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--ink-light);
}
</style>
