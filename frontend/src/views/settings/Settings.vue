<template>
  <div class="page-container">
    <h2 class="page-title">我的</h2>

    <!-- 用户信息 -->
    <div class="ink-card profile-card">
      <div class="profile-row">
        <el-upload
          class="avatar-uploader"
          :show-file-list="false"
          :before-upload="handleAvatar"
          accept="image/*"
        >
          <el-avatar :size="60" :src="assetUrl(store.user?.avatar)">
            {{ store.user?.nickname?.charAt(0) || 'U' }}
          </el-avatar>
          <div class="avatar-mask">换头像</div>
        </el-upload>
        <div class="profile-info">
          <div class="nickname">{{ store.user?.nickname }}</div>
          <div class="phone">{{ store.user?.email }}</div>
        </div>
        <el-button text @click="editName = true">编辑</el-button>
      </div>
    </div>

    <!-- 设置 -->
    <div class="section-title">设置</div>
    <div class="ink-card menu-card">
      <div v-if="!store.hasCouple" class="menu-item bind-entry" @click="$router.push('/bind')">
        <el-icon><Connection /></el-icon><span>情侣绑定</span>
        <em>未绑定</em><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
      <div v-if="store.hasCouple" class="menu-item" @click="openChatBg">
        <el-icon><Picture /></el-icon><span>聊天背景</span><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
      <div class="menu-item">
        <el-icon><Bell /></el-icon><span>消息通知</span>
        <el-switch v-model="notifyEnabled" @change="toggleNotify" />
      </div>
      <div v-if="store.isAdmin" class="menu-item" @click="$router.push('/admin')">
        <el-icon><Setting /></el-icon><span>后台管理</span><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
      <div class="menu-item" @click="logout">
        <el-icon><SwitchButton /></el-icon><span>退出登录</span><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
      <div class="menu-item" @click="$router.push('/reset-password')">
        <el-icon><Setting /></el-icon><span>设置 / 重置密码</span><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
      <div v-if="store.hasCouple" class="menu-item danger" @click="dissolve">
        <el-icon><CircleClose /></el-icon><span>解除情侣关系</span><el-icon class="arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <!-- 编辑昵称 -->
    <el-dialog v-model="editName" title="修改昵称" width="85%">
      <el-input v-model="newName" placeholder="请输入新昵称" />
      <template #footer>
        <el-button @click="editName = false">取消</el-button>
        <el-button type="primary" @click="saveName">保存</el-button>
      </template>
    </el-dialog>

    <!-- 聊天背景设置 -->
    <el-dialog v-model="showChatBg" title="聊天背景" width="92%">
      <div class="bg-section">
        <div class="bg-section-title">内置预设</div>
        <div class="bg-presets">
          <div
            v-for="p in presets"
            :key="p.key"
            class="preset-item"
            :class="{ active: currentBg === `preset:${p.key}` }"
            @click="choosePreset(p.key)"
          >
            <div class="preset-thumb" :style="p.style"></div>
            <span class="preset-name">{{ p.name }}</span>
          </div>
        </div>
      </div>
      <div class="bg-section">
        <div class="bg-section-title">自定义图片</div>
        <el-upload
          :show-file-list="false"
          :before-upload="handleChatBg"
          accept="image/*"
        >
          <el-button>上传自定义背景</el-button>
        </el-upload>
      </div>
      <template #footer>
        <el-button @click="resetBg">恢复默认</el-button>
        <el-button type="primary" @click="showChatBg = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Bell, Setting, ArrowRight, SwitchButton, CircleClose, Picture, Connection } from '@element-plus/icons-vue'
import { useUserStore } from '../../stores/user'
import { authApi, settingsApi, assetUrl } from '../../api'
import { preprocessImage } from '../../utils/image'

const store = useUserStore()
const router = useRouter()
const notifyEnabled = ref(true)
const editName = ref(false)
const newName = ref('')
const showChatBg = ref(false)
const currentBg = ref('')

const presets = [
  { key: 'default', name: '默认', style: { background: 'var(--bg-paper)' } },
  { key: 'cream', name: '奶黄', style: { background: 'linear-gradient(135deg, #faf5ec 0%, #faf0f0 100%)' } },
  { key: 'mint', name: '薄荷', style: { background: 'linear-gradient(135deg, #eef5f2 0%, #edf4f7 100%)' } },
  { key: 'sunset', name: '日落', style: { background: 'linear-gradient(135deg, #faf0f0 0%, #faf5ec 50%, #edf4f7 100%)' } },
  { key: 'lavender', name: '薰衣草', style: { background: 'linear-gradient(135deg, #f1edf7 0%, #f5edf5 100%)' } },
  { key: 'ink', name: '水墨', style: { background: 'linear-gradient(135deg, #f7f5f0 0%, #f1edf7 100%)' } },
]

const handleAvatar = async (file) => {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 50MB')
    return false
  }
  try {
    const processed = await preprocessImage(file, { maxSize: 256, quality: 0.9 })
    const res = await authApi.uploadAvatar(processed)
    await store.fetchUser()
    ElMessage.success('头像已更新')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '头像上传失败')
  }
  return false
}

const openChatBg = async () => {
  showChatBg.value = true
  try {
    const info = await settingsApi.coupleInfo()
    currentBg.value = info.chat_bg || ''
  } catch {}
}

const choosePreset = async (key) => {
  try {
    await settingsApi.setChatBgPreset(key)
    currentBg.value = `preset:${key}`
    ElMessage.success('已应用')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '设置失败')
  }
}

const handleChatBg = async (file) => {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 50MB')
    return false
  }
  try {
    const processed = await preprocessImage(file)
    const res = await settingsApi.uploadChatBg(processed)
    currentBg.value = res.url
    ElMessage.success('背景已更新')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
  return false
}

const resetBg = async () => {
  try {
    await settingsApi.resetChatBg()
    currentBg.value = ''
    ElMessage.success('已恢复默认')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '恢复失败')
  }
}

const toggleNotify = async (val) => {
  try {
    await settingsApi.toggleNotify(val)
    ElMessage.success(`通知已${val ? '开启' : '关闭'}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '设置失败')
    notifyEnabled.value = !val
  }
}

const saveName = async () => {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入昵称')
    return
  }
  try {
    await authApi.updateProfile({ nickname: newName.value })
    await store.fetchUser()
    ElMessage.success('已修改')
    editName.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '修改昵称失败')
  }
}

const logout = async () => {
  try {
    await ElMessageBox.confirm('确定退出登录？', '提示')
    store.logout()
    router.push('/login')
  } catch {
    // 用户取消确认
  }
}

const dissolve = async () => {
  try {
    await ElMessageBox.confirm('解除后双方数据保留但无法再互动，确定？', '解除情侣关系', { type: 'warning' })
  } catch {
    return
  }
  try {
    await authApi.dissolveCouple()
    await store.fetchUser()
    ElMessage.success('已解除')
    router.push('/bind')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '解除失败')
  }
}

onMounted(() => {
  notifyEnabled.value = store.user?.notify_enabled ?? true
  newName.value = store.user?.nickname || ''
})
</script>

<style scoped>
.profile-card {
  margin-bottom: 20px;
}
.profile-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.avatar-uploader {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  cursor: pointer;
  overflow: hidden;
  flex-shrink: 0;
}
.avatar-uploader :deep(.el-upload) {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  position: relative;
}
.avatar-mask {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: rgba(0,0,0,0.45);
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}
.avatar-uploader:hover .avatar-mask {
  opacity: 1;
}
.profile-info {
  flex: 1;
}
.nickname {
  font-size: 17px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.phone {
  font-size: 13px;
  color: var(--ink-secondary);
  margin-top: 2px;
}
.section-title {
  font-size: 14px;
  color: var(--ink-secondary);
  margin: 16px 0 8px;
  padding-left: 4px;
}
.menu-card {
  padding: 0;
  overflow: hidden;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-soft);
  font-size: 15px;
  color: var(--ink-primary);
  cursor: pointer;
}
.menu-item:last-child {
  border-bottom: none;
}
.menu-item.danger {
  color: var(--accent-rose);
}
.menu-item.bind-entry {
  color: var(--accent-rose);
}
.menu-item em {
  color: var(--accent-rose);
  font-size: 12px;
  font-style: normal;
}
.menu-item span {
  flex: 1;
}
.arrow {
  color: var(--ink-light);
}

/* 聊天背景弹窗 */
.bg-section {
  margin-bottom: 18px;
}
.bg-section-title {
  font-size: 13px;
  color: var(--ink-secondary);
  margin-bottom: 10px;
}
.bg-presets {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.preset-item {
  text-align: center;
  cursor: pointer;
}
.preset-thumb {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  margin-bottom: 4px;
  transition: border-color 0.2s;
}
.preset-item.active .preset-thumb {
  border-color: var(--accent-rose);
}
.preset-name {
  font-size: 12px;
  color: var(--ink-secondary);
}
.preset-item.active .preset-name {
  color: var(--accent-rose);
  font-weight: 600;
}
</style>
