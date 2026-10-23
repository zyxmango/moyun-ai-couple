<template>
  <div class="layout" :class="{ 'chat-layout': route.path === '/chat' }" :style="viewportStyle">
    <div class="layout-content">
      <router-view />
    </div>
    <CoupleAssistantWidget
      v-if="store.hasCouple && !isAdminRoute"
      :class="{ 'chat-offset': route.path === '/chat' }"
    />
    <nav class="bottom-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path), emphasized: item.emphasized }"
      >
        <el-icon :size="22"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { ChatDotRound, MagicStick, Notebook, Setting, HomeFilled } from '@element-plus/icons-vue'
import CoupleAssistantWidget from '../components/CoupleAssistantWidget.vue'

const route = useRoute()
const store = useUserStore()
const viewportStyle = ref({})
const updateViewport = () => {
  const viewport = window.visualViewport
  viewportStyle.value = {
    '--visible-height': `${viewport?.height ?? window.innerHeight}px`,
    '--visible-top': `${viewport?.offsetTop ?? 0}px`,
  }
}
onMounted(() => {
  updateViewport()
  window.addEventListener('resize', updateViewport)
  window.visualViewport?.addEventListener('resize', updateViewport)
  window.visualViewport?.addEventListener('scroll', updateViewport)
})
onUnmounted(() => {
  window.removeEventListener('resize', updateViewport)
  window.visualViewport?.removeEventListener('resize', updateViewport)
  window.visualViewport?.removeEventListener('scroll', updateViewport)
})

const isAdminRoute = computed(() => route.path.startsWith('/admin'))

const navItems = computed(() => {
  if (isAdminRoute.value) {
    return [
      { path: '/admin/stats', label: '概览', icon: 'DataAnalysis' },
      { path: '/admin/users', label: '用户', icon: 'User' },
      { path: '/admin/couples', label: '情侣', icon: 'Connection' },
      { path: '/admin/logs', label: '日志', icon: 'Document' },
      { path: '/', label: '返回', icon: 'Back' },
    ]
  }
  return [
    { path: '/', label: '首页', icon: HomeFilled },
    { path: '/life', label: '生活', icon: Notebook },
    { path: '/chat', label: '聊天', icon: ChatDotRound, emphasized: true },
    { path: '/ai', label: 'AI', icon: MagicStick },
    { path: '/settings', label: '我的', icon: Setting },
  ]
})

const isActive = (path) => {
  if (path === '/') return route.path === '/' || route.path === '/home'
  return route.path.startsWith(path)
}
</script>

<style scoped>
.layout {
  --nav-height: calc(64px + env(safe-area-inset-bottom, 0px));
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  padding-bottom: var(--nav-height);
}
.layout-content {
  flex: 1;
  min-height: 0;
}
.chat-layout { position:fixed; top:var(--visible-top, 0px); left:0; right:0; height:var(--visible-height, 100dvh); min-height:0; overflow:hidden; }
.chat-layout .layout-content { display:flex; overflow:hidden; }
.chat-layout .bottom-nav { position:absolute; }
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  max-width: 720px;
  margin: 0 auto;
  height: var(--nav-height);
  padding: 0 10px env(safe-area-inset-bottom, 0px);
  background: rgba(255, 253, 249, 0.96);
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--border-soft);
  display: flex;
  align-items: center;
  justify-content: space-around;
  z-index: 100;
  box-shadow: 0 -2px 12px rgba(44, 44, 44, 0.04);
}
.nav-item {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: var(--ink-light);
  text-decoration: none;
  padding: 6px 4px;
  border-radius: 10px;
  transition: color 0.2s, background 0.2s;
}
.nav-item.emphasized :deep(.el-icon) {
  width: 42px;
  height: 42px;
  margin-top: -22px;
  border: 4px solid #f7f4ef;
  border-radius: 50%;
  color: #fff;
  background: var(--accent-rose);
  box-shadow: 0 7px 18px rgba(189, 108, 104, 0.28);
}
.nav-item.emphasized span { margin-top: -1px; }
.nav-item.active {
  color: var(--accent-rose);
}
.nav-item span {
  letter-spacing: 0.5px;
}
</style>
