<template>
  <div class="page-container gen-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="title-wrap">
        <h2 class="page-title">AI 内容生成</h2>
        <p class="page-sub">为你们的时光添一份浪漫笔墨</p>
      </div>
      <div class="deco-line"></div>
    </div>

    <!-- 场景选择卡片 -->
    <div class="scene-grid">
      <div
        v-for="s in scenes"
        :key="s.key"
        class="scene-card ink-card"
        :class="{ active: form.scene === s.key }"
        :style="{ '--scene-color': s.color, '--scene-bg': s.bg }"
        @click="chooseScene(s.key)"
      >
        <div class="scene-icon">
          <el-icon :size="26"><component :is="s.icon" /></el-icon>
        </div>
        <div class="scene-info">
          <div class="scene-name">{{ s.name }}</div>
          <div class="scene-desc">{{ s.desc }}</div>
        </div>
        <div v-if="form.scene === s.key" class="scene-check">
          <el-icon><Check /></el-icon>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="ink-card form-card">
      <div class="form-label">
        <span class="dot"></span>
        <span>创作灵感</span>
      </div>
      <div class="form-tip">{{ scenes.find(s => s.key === form.scene)?.tip }}</div>
      <el-input
        v-model="form.keywords"
        class="keyword-input"
        :placeholder="scenes.find(s => s.key === form.scene)?.placeholder"
        size="large"
      />
      <div class="tag-list" v-if="suggests.length > 0">
        <span
          v-for="t in suggests"
          :key="t"
          class="suggest-tag"
          @click="appendTag(t)"
        >{{ t }}</span>
      </div>
      <el-form-item label="风格偏好（可选）" class="extra-form">
        <el-input
          v-model="form.extra"
          type="textarea"
          :rows="2"
          placeholder="如：文艺古风、俏皮可爱、深情浪漫、幽默风趣..."
        />
      </el-form-item>
      <el-button class="gen-btn" type="rose" :loading="loading" @click="generate">
        <el-icon class="btn-icon"><MagicStick /></el-icon>
        <span>生成内容</span>
      </el-button>
    </div>

    <!-- 结果卡片 -->
    <transition name="fade">
      <div v-if="result" class="ink-card result-card">
        <div class="result-head">
          <div class="result-badge">
            <el-icon :size="14"><MagicStick /></el-icon>
            <span>生成结果</span>
          </div>
          <div class="result-actions">
            <el-button text @click="copyResult" size="small">
              <el-icon><DocumentCopy /></el-icon>复制
            </el-button>
            <el-button text @click="regenerate" size="small">
              <el-icon><Refresh /></el-icon>换一条
            </el-button>
          </div>
        </div>
        <div class="result-divider"></div>
        <div class="result-body">
          <div class="result-text">{{ result }}</div>
        </div>
      </div>
    </transition>

    <!-- 历史记录 -->
    <div v-if="history.length > 0" class="history-block">
      <div class="block-title">
        <span>历史作品</span>
        <el-button v-if="history.length > 0" text size="small" @click="clearHistory">清空</el-button>
      </div>
      <div
        v-for="(h, i) in history"
        :key="i"
        class="ink-card hist-card"
        @click="showHist(h)"
      >
        <div class="hist-scene" :style="{ background: getScene(h.scene)?.bg }">
          <el-icon :size="18" :color="getScene(h.scene)?.color">
            <component :is="getScene(h.scene)?.icon" />
          </el-icon>
        </div>
        <div class="hist-body">
          <div class="hist-preview">{{ h.content.slice(0, 40) }}{{ h.content.length > 40 ? '...' : '' }}</div>
          <div class="hist-meta">
            <span class="hist-kw">{{ h.keywords }}</span>
            <span class="hist-time">{{ formatTime(h.time) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Calendar, Location, EditPen, Check, MagicStick, Refresh, DocumentCopy,
} from '@element-plus/icons-vue'
import { aiApi } from '../../api'

const STORAGE_KEY = 'gen_history_v1'

const scenes = [
  {
    key: 'anniversary',
    name: '纪念日文案',
    desc: '恋爱周年 / 生日 / 节日祝福',
    icon: Calendar,
    color: '#c96b6b',
    bg: '#faf0f0',
    placeholder: '如：三周年、第一次见面、海边求婚...',
    tip: '告诉 AI 你们的特殊日子，它会为你们定制专属寄语。',
    suggests: ['三周年', '在一起100天', 'TA的生日', '情人节'],
  },
  {
    key: 'date',
    name: '约会方案',
    desc: '周末约会 / 惊喜行程 / 餐厅推荐',
    icon: Location,
    color: '#5e8b7e',
    bg: '#eef5f2',
    placeholder: '如：周末两天、预算500、北京、文艺...',
    tip: '描述城市、预算、偏好，AI 会规划一场难忘的约会。',
    suggests: ['周末野餐', '文艺咖啡馆', '看日落', '手作DIY'],
  },
  {
    key: 'keyword',
    name: '个性文案',
    desc: '朋友圈 / 便签 / 情书 / 告白',
    icon: EditPen,
    color: '#c9a96e',
    bg: '#f7f2e9',
    placeholder: '如：雨后的咖啡馆、喜欢了很久...',
    tip: '写几个关键词或一句话，AI 会帮你润色成优美文案。',
    suggests: ['朋友圈晒照', '给TA的情书', '晚安情话', '告白'],
  },
]

const form = reactive({ scene: 'anniversary', keywords: '', extra: '' })
const result = ref('')
const loading = ref(false)
const history = ref([])

const suggests = computed(() => {
  const s = scenes.find(x => x.key === form.scene)
  return s?.suggests || []
})

const chooseScene = (key) => {
  form.scene = key
}

const appendTag = (t) => {
  form.keywords = form.keywords ? `${form.keywords}、${t}` : t
}

const getScene = (key) => scenes.find(s => s.key === key)

const formatTime = (t) => {
  const d = new Date(t)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) {
    return `今天 ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  }
  const y = new Date(now - 86400000)
  if (d.toDateString() === y.toDateString()) {
    return `昨天 ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

const loadHistory = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    history.value = raw ? JSON.parse(raw) : []
  } catch { history.value = [] }
}

const saveHistory = (item) => {
  history.value.unshift(item)
  if (history.value.length > 20) history.value = history.value.slice(0, 20)
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value)) } catch {}
}

const clearHistory = async () => {
  try {
    await ElMessageBox.confirm('确定清空历史记录？', '提示', { type: 'warning' })
    history.value = []
    localStorage.removeItem(STORAGE_KEY)
    ElMessage.success('已清空')
  } catch {}
}

const generate = async (retry = false) => {
  if (!form.keywords.trim()) {
    ElMessage.warning('请输入关键词或灵感')
    return
  }
  loading.value = true
  try {
    const payload = { ...form }
    if (retry) payload.retry = true
    const res = await aiApi.generate(payload)
    result.value = res.content
    saveHistory({
      scene: form.scene,
      keywords: form.keywords,
      content: res.content,
      time: Date.now(),
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '生成失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const regenerate = () => generate(true)

const copyResult = () => {
  if (!result.value) return
  navigator.clipboard.writeText(result.value)
    .then(() => ElMessage.success('已复制到剪贴板 ♥'))
    .catch(() => {
      const ta = document.createElement('textarea')
      ta.value = result.value
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      ElMessage.success('已复制 ♥')
    })
}

const showHist = (h) => {
  form.scene = h.scene
  form.keywords = h.keywords
  result.value = h.content
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

loadHistory()
</script>

<style scoped>
.gen-page {
  padding-bottom: 40px;
}
.page-header {
  padding: 8px 4px 18px;
  position: relative;
}
.title-wrap {
  position: relative;
  z-index: 1;
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
  background: linear-gradient(90deg, var(--accent-rose), var(--accent-gold));
  border-radius: 2px;
}

/* 场景卡片 */
.scene-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.scene-card {
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  position: relative;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.25s ease;
}
.scene-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-hover);
}
.scene-card.active {
  border-color: var(--scene-color);
  background: var(--scene-bg);
  box-shadow: var(--shadow-hover);
}
.scene-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--scene-bg);
  color: var(--scene-color);
  display: flex;
  align-items: center;
  justify-content: center;
}
.scene-card.active .scene-icon {
  background: var(--scene-color);
  color: #fff;
}
.scene-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.scene-desc {
  font-size: 11px;
  color: var(--ink-secondary);
  line-height: 1.4;
  margin-top: 2px;
}
.scene-check {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--scene-color);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

/* 表单卡片 */
.form-card {
  margin-bottom: 16px;
}
.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-darkest);
  margin-bottom: 4px;
}
.form-label .dot {
  width: 4px;
  height: 16px;
  background: linear-gradient(180deg, var(--accent-rose), var(--accent-gold));
  border-radius: 2px;
}
.form-tip {
  font-size: 12px;
  color: var(--ink-light);
  margin-bottom: 12px;
  padding-left: 12px;
  line-height: 1.5;
}
.keyword-input {
  margin-bottom: 12px;
}
.extra-form {
  margin-top: 10px;
}
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.suggest-tag {
  padding: 5px 12px;
  background: var(--bg-soft);
  border-radius: 100px;
  font-size: 12px;
  color: var(--ink-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.suggest-tag:hover {
  background: var(--accent-rose-bg);
  color: var(--accent-rose);
}
.gen-btn {
  width: 100%;
  height: 44px;
  margin-top: 6px;
  font-size: 15px;
  border-radius: var(--radius-md);
}
.btn-icon {
  margin-right: 6px;
}

/* 结果卡片 */
.result-card {
  margin-bottom: 20px;
  background: linear-gradient(180deg, #fefbfa 0%, #ffffff 100%);
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
}
.result-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: var(--accent-rose-bg);
  color: var(--accent-rose);
  border-radius: 100px;
  font-size: 12px;
  font-weight: 600;
}
.result-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-soft), transparent);
  margin: 14px 0;
}
.result-body {
  padding: 8px 4px;
}
.result-text {
  font-size: 15px;
  line-height: 1.9;
  color: var(--ink-primary);
  white-space: pre-wrap;
  letter-spacing: 0.3px;
}

/* 历史记录 */
.history-block {
  margin-top: 24px;
}
.block-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-secondary);
}
.hist-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s;
}
.hist-card:hover {
  transform: translateX(2px);
  box-shadow: var(--shadow-hover);
}
.hist-scene {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.hist-preview {
  font-size: 14px;
  color: var(--ink-primary);
  line-height: 1.5;
  margin-bottom: 6px;
}
.hist-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hist-kw {
  font-size: 11px;
  color: var(--accent-rose);
  background: var(--accent-rose-bg);
  padding: 2px 8px;
  border-radius: 6px;
}
.hist-time {
  font-size: 11px;
  color: var(--ink-light);
}

@media (max-width: 480px) {
  .scene-grid {
    grid-template-columns: 1fr 1fr;
  }
  .scene-card:last-child {
    grid-column: span 2;
    flex-direction: row;
    align-items: center;
    gap: 12px;
  }
  .scene-card:last-child .scene-info {
    flex: 1;
  }
}
@media (max-width: 360px) {
  .scene-grid {
    grid-template-columns: 1fr;
  }
  .scene-card {
    flex-direction: row !important;
    align-items: center !important;
  }
  .scene-card .scene-info {
    flex: 1;
  }
}
</style>
