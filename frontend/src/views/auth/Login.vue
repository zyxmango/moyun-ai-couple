<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <h1>墨韵</h1>
        <p>为真实情侣打造的共享记忆 AI</p>
      </div>
      <el-tabs v-model="loginMode" stretch class="login-tabs">
        <el-tab-pane label="验证码登录" name="code" />
        <el-tab-pane label="密码登录" name="password" />
      </el-tabs>
      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱地址" />
        </el-form-item>
        <el-form-item v-if="loginMode === 'code'" label="验证码">
          <div class="code-row">
            <el-input v-model="form.code" placeholder="请输入验证码" maxlength="6" />
            <el-button :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item v-else label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" @keyup.enter="handleLogin" />
        </el-form-item>
        <el-button type="primary" class="auth-btn" :loading="loading" @click="handleLogin">登 录</el-button>
        <div v-if="loginMode === 'password'" class="auth-footer"><router-link :to="{ path: '/reset-password', query: { email: form.email.trim() } }">忘记密码 / 首次设置密码</router-link></div>
        <div class="auth-footer">
          还没有账号？<router-link to="/register">立即注册</router-link>
        </div>
      </el-form>
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
const loading = ref(false)
const countdown = ref(0)
const loginMode = ref('code')
const form = ref({ email: '', code: '', password: '' })

const sendCode = async () => {
  if (!form.value.email) {
    ElMessage.warning('请输入邮箱地址')
    return
  }
  try {
    const res = await authApi.sendCode(form.value.email)
    if (res.code) {
      form.value.code = res.code
      ElMessage.warning(`本地测试验证码：${res.code}（已自动填入）`)
    } else {
      ElMessage.success('验证码已发送到邮箱，请查收')
    }
    countdown.value = 60
    const timer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) clearInterval(timer)
    }, 1000)
  } catch { /* 统一接口错误提示 */ }
}

const handleLogin = async () => {
  if (!form.value.email || (loginMode.value === 'code' ? !form.value.code : !form.value.password)) {
    ElMessage.warning(loginMode.value === 'code' ? '请填写邮箱和验证码' : '请填写邮箱和密码')
    return
  }
  loading.value = true
  try {
    const res = loginMode.value === 'code'
      ? await authApi.loginCode({ email: form.value.email, code: form.value.code })
      : await authApi.login({ email: form.value.email, password: form.value.password })
    store.setToken(res.access_token)
    await store.fetchUser()
    ElMessage.success('登录成功')
    router.push('/')
  } catch { /* 统一接口错误提示 */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-paper) 0%, var(--accent-rose-bg) 100%);
  padding: 24px;
}
.auth-card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: 40px 32px;
  box-shadow: var(--shadow-hover);
}
.auth-header {
  text-align: center;
  margin-bottom: 32px;
}
.auth-header h1 {
  font-size: 36px;
  font-weight: 700;
  color: var(--ink-darkest);
  letter-spacing: 8px;
  margin-bottom: 8px;
}
.auth-header p {
  color: var(--ink-secondary);
  font-size: 14px;
  letter-spacing: 2px;
}
.login-tabs { margin-bottom:18px; }
.code-row {
  display: flex;
  gap: 10px;
  width: 100%;
}
.code-row .el-input {
  flex: 1;
}
.auth-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  letter-spacing: 4px;
  margin-top: 8px;
}
.auth-footer {
  text-align: center;
  margin-top: 20px;
  font-size: 14px;
  color: var(--ink-secondary);
}
.auth-footer a {
  color: var(--accent-rose);
  text-decoration: none;
}
</style>
