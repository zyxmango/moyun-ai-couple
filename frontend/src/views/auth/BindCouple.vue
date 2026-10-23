<template>
  <div class="bind-page">
    <div class="bind-card">
      <div class="auth-header">
        <h1>情侣绑定</h1>
        <p>将你们的账号关联在一起</p>
      </div>

      <el-tabs v-model="activeTab" stretch>
        <el-tab-pane label="生成配对码" name="generate">
          <div class="tab-content">
            <p class="tip">生成配对码后，让另一半输入此码完成绑定</p>
            <el-button type="primary" class="auth-btn" :loading="generating" @click="generate">生成配对码</el-button>
            <div v-if="pairingCode" class="code-display">
              <div class="code-label">你的配对码</div>
              <div class="code-num">{{ pairingCode }}</div>
              <el-button text @click="copyCode">复制</el-button>
            </div>
            <div v-if="pairingCode" class="waiting-tip">
              等待另一半绑定...
              <el-button link type="primary" @click="checkStatus">刷新状态</el-button>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="输入配对码" name="bind">
          <div class="tab-content">
            <p class="tip">输入对方生成的配对码完成绑定</p>
            <el-input v-model="bindCode" placeholder="请输入6位配对码" maxlength="6" size="large" class="code-input" />
            <el-button type="rose" class="auth-btn" :loading="binding" @click="bind">绑定</el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../../api'
import { useUserStore } from '../../stores/user'

const router = useRouter()
const store = useUserStore()
const activeTab = ref('generate')
const generating = ref(false)
const binding = ref(false)
const pairingCode = ref('')
const bindCode = ref('')

const generate = async () => {
  generating.value = true
  try {
    const res = await authApi.generatePairingCode()
    pairingCode.value = res.pairing_code
    ElMessage.success('配对码已生成')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '生成配对码失败')
  } finally {
    generating.value = false
  }
}

const copyCode = () => {
  navigator.clipboard.writeText(pairingCode.value)
    .then(() => ElMessage.success('已复制'))
    .catch(() => ElMessage.warning('复制失败，请手动复制'))
}

const checkStatus = async () => {
  try {
    await store.fetchUser()
    if (store.hasCouple) {
      ElMessage.success('绑定成功！')
      router.push('/chat')
    } else {
      ElMessage.info('对方尚未绑定')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '刷新状态失败')
  }
}

const bind = async () => {
  if (!bindCode.value) {
    ElMessage.warning('请输入配对码')
    return
  }
  binding.value = true
  try {
    await authApi.bindCouple(bindCode.value)
    await store.fetchUser()
    ElMessage.success('配对成功！')
    router.push('/chat')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '绑定失败，请检查配对码是否正确')
  } finally {
    binding.value = false
  }
}
</script>

<style scoped>
.bind-page {
  min-height: calc(100vh - 60px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-paper) 0%, var(--accent-rose-bg) 100%);
  padding: 24px;
}
.bind-card {
  width: 100%;
  max-width: 400px;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: 36px 32px;
  box-shadow: var(--shadow-hover);
}
.auth-header {
  text-align: center;
  margin-bottom: 24px;
}
.auth-header h1 {
  font-size: 26px;
  font-weight: 700;
  color: var(--ink-darkest);
  letter-spacing: 4px;
}
.auth-header p {
  color: var(--ink-secondary);
  font-size: 14px;
  margin-top: 6px;
}
.tab-content {
  padding: 16px 0;
  text-align: center;
}
.tip {
  color: var(--ink-secondary);
  font-size: 14px;
  margin-bottom: 20px;
  line-height: 1.6;
}
.auth-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  margin-top: 12px;
}
.code-display {
  margin-top: 24px;
  padding: 20px;
  background: var(--bg-soft);
  border-radius: var(--radius-md);
}
.code-label {
  font-size: 13px;
  color: var(--ink-secondary);
  margin-bottom: 8px;
}
.code-num {
  font-size: 36px;
  font-weight: 700;
  color: var(--accent-rose);
  letter-spacing: 8px;
}
.waiting-tip {
  margin-top: 16px;
  font-size: 14px;
  color: var(--ink-secondary);
}
.code-input {
  margin-bottom: 8px;
}
.code-input :deep(.el-input__inner) {
  text-align: center;
  letter-spacing: 6px;
  font-size: 20px;
}
</style>
