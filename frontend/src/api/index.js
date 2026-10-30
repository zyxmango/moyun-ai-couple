import axios from 'axios'
import { ElMessage } from 'element-plus'

// API 基址：打包成 APK 时通过环境变量 VITE_API_BASE 指向后端公网地址（如 ngrok）；
// 本地开发时留空，走 vite.config.js 的 proxy 转发到 localhost:8000
export const API_BASE = import.meta.env.VITE_API_BASE || ''

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  timeout: 30000,
})

// 将后端返回的 /uploads/xxx 相对路径拼接为完整 URL
// APK 运行在 WebView 里，相对路径无法命中后端，必须拼成绝对地址
export const assetUrl = (path) => {
  if (!path) return ''
  if (/^(https?:)?\/\//.test(path)) return path
  if (path.startsWith('/uploads/')) return API_BASE + path
  return path
}

// 请求拦截：附加 token + 跳过 ngrok 警告页（免费版首次访问会拦截返回 HTML 警告）
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // ngrok 免费版首次访问会返回警告页而非转发后端，需加此 header 跳过
  if (API_BASE) {
    config.headers['ngrok-skip-browser-warning'] = 'true'
  }
  return config
})

// 响应拦截：统一错误处理
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map(item => item.msg || '输入格式不正确').join('；')
      : (typeof detail === 'string' ? detail : error.message || '请求失败')
    const isExpectedUnpairedState =
      error.response?.status === 400 &&
      (msg.includes('未绑定情侣关系') || msg.includes('尚未绑定情侣'))
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      ElMessage.error('登录已过期，请重新登录')
      setTimeout(() => {
        window.location.href = '/login'
      }, 1500)
    } else if (!isExpectedUnpairedState) {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

// ---------- 认证 ----------
export const authApi = {
  sendCode: (email, purpose = 'general') => api.post('/auth/send-code', { email, purpose }),
  resetPassword: (data) => api.post('/auth/reset-password', data),
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  loginCode: (data) => api.post('/auth/login-code', data),
  me: () => api.get('/auth/me'),
  updateProfile: (data) => api.put('/auth/profile', data),
  uploadAvatar: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/auth/avatar', form)
  },
  generatePairingCode: () => api.post('/auth/couple/generate'),
  bindCouple: (pairing_code) => api.post('/auth/couple/bind', { pairing_code }),
  dissolveCouple: () => api.post('/auth/couple/dissolve'),
  logout: () => api.post('/auth/logout'),
}

// ---------- 聊天 ----------
export const chatApi = {
  history: (params) => api.get('/chat/history', { params }),
  count: () => api.get('/chat/count'),
  calendar: (timezoneOffset = -new Date().getTimezoneOffset()) => api.get('/chat/calendar', { params: { timezone_offset: timezoneOffset } }),
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/chat/upload', form)
  },
  unreadCount: () => api.get('/chat/unread-count'),
}

// ---------- 纪念日 ----------
export const anniversaryApi = {
  list: () => api.get('/anniversaries'),
  create: (data) => api.post('/anniversaries', data),
  update: (id, data) => api.put(`/anniversaries/${id}`, data),
  delete: (id) => api.delete(`/anniversaries/${id}`),
}

// ---------- 相册 ----------
export const albumApi = {
  list: () => api.get('/album'),
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/album', form)
  },
  delete: (id) => api.delete(`/album/${id}`),
}

// ---------- 日记 ----------
export const diaryApi = {
  list: () => api.get('/diaries'),
  create: (data) => api.post('/diaries', data),
  get: (id) => api.get(`/diaries/${id}`),
  update: (id, data) => api.put(`/diaries/${id}`, data),
  delete: (id) => api.delete(`/diaries/${id}`),
}

// ---------- AI ----------
export const aiApi = {
  companionChat: (data) => api.post('/ai/companion/chat', {
    message: data.user_message ?? data.message,
    conversation_id: data.conversation_id,
  }),
  companionHistory: (params) => api.get('/ai/companion/history', { params }),
  generate: (data) => api.post('/ai/generate', data),
  summary: (data) => api.post('/ai/summary/daily', data),
  summaryList: () => api.get('/ai/summary/list'),
  reminders: () => api.get('/ai/reminders'),
}

// ---------- RAG ----------
export const ragApi = {
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/rag/upload', form)
  },
  uploadText: (data) => api.post('/rag/upload-text', data),
  documents: () => api.get('/rag/documents'),
  deleteDoc: (id) => api.delete(`/rag/documents/${id}`),
  chat: (data) => api.post('/rag/chat', data),
  history: (params) => api.get('/rag/history', { params }),
}

// ---------- AI 共同记忆 ----------
export const memoryApi = {
  settings: () => api.get('/ai/memory/settings'),
  updateSettings: (data) => api.put('/ai/memory/settings', data),
  sync: () => api.post('/ai/memory/sync'),
  list: (params) => api.get('/ai/memory', { params }),
  createManual: (data) => api.post('/ai/memory/manual', data),
  extract: () => api.post('/ai/memory/extract'),
  review: (id, data) => api.patch(`/ai/memory/${id}`, data),
  evidence: (id) => api.get(`/ai/memory/${id}/evidence`),
  delete: (id) => api.delete(`/ai/memory/${id}`),
  clear: () => api.delete('/ai/memory', { params: { confirm: true } }),
  chat: (data) => api.post('/ai/memory/chat', data),
  report: (days = 7) => api.post('/ai/memory/report', null, { params: { days } }),
  todayQuestion: () => api.get('/ai/memory/daily-question/today'),
  answerQuestion: (id, content) => api.post(`/ai/memory/daily-question/${id}/answer`, { content }),
}

// ---------- AI 约会规划 ----------
export const datePlanApi = {
  create: (data) => api.post('/ai/date-plan', data),
  history: (limit = 10) => api.get('/ai/date-plan', { params: { limit } }),
}

// ---------- 设置 ----------
export const settingsApi = {
  toggleNotify: (enabled) => api.put('/settings/notify', null, { params: { enabled } }),
  coupleInfo: () => api.get('/couple/info'),
  setRelationshipDate: (relationship_start_date) => api.put('/couple/relationship-date', { relationship_start_date }),
  uploadHeroBg: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/couple/hero-bg', form)
  },
  resetHeroBg: () => api.delete('/couple/hero-bg'),
  setChatBgPreset: (key) => api.put('/couple/chat-bg/preset', null, { params: { key } }),
  uploadChatBg: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/couple/chat-bg', form)
  },
  resetChatBg: () => api.delete('/couple/chat-bg'),
}

// ---------- 菜谱 ----------
export const recipeApi = {
  list: (params) => api.get('/recipes', { params }),
  get: (id) => api.get(`/recipes/${id}`),
  random: () => api.get('/recipes/random'),
  create: (data) => api.post('/recipes', data),
  update: (id, data) => api.put(`/recipes/${id}`, data),
  delete: (id) => api.delete(`/recipes/${id}`),
  rate: (id, score) => api.post(`/recipes/${id}/rate`, null, { params: { score } }),
  cook: (id) => api.post(`/recipes/${id}/cook`),
  toggleWantEat: (id) => api.put(`/recipes/${id}/want-eat`),
  comments: (id) => api.get(`/recipes/${id}/comments`),
  addComment: (id, content) => api.post(`/recipes/${id}/comments`, { content }),
  deleteComment: (id, commentId) => api.delete(`/recipes/${id}/comments/${commentId}`),
  uploadCover: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/recipes/upload-cover', form)
  },
}

// ---------- 管理后台 ----------
export const adminApi = {
  stats: () => api.get('/admin/stats'),
  memoryHealth: () => api.get('/admin/memory-health'),
  users: () => api.get('/admin/users'),
  couples: () => api.get('/admin/couples'),
  aiLogs: (params) => api.get('/admin/ai-logs', { params }),
}

export default api
