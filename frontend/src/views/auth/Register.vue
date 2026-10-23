<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <h1>注册</h1>
        <p>开启你们的专属空间</p>
      </div>
      <el-form :model="form" label-position="top">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="请输入邮箱地址" />
        </el-form-item>
        <el-form-item label="验证码">
          <div class="code-row">
            <el-input v-model="form.code" placeholder="请输入验证码" maxlength="6" />
            <el-button :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </el-button>
          </div>
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" placeholder="设置密码（至少 8 位）" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="confirmPassword" type="password" show-password autocomplete="new-password" placeholder="再次输入密码" />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="form.nickname" placeholder="给自己起个昵称" />
        </el-form-item>
        <el-button type="primary" class="auth-btn" :loading="loading" @click="handleRegister">注 册</el-button>
        <div class="auth-footer">
          已有账号？<router-link to="/login">去登录</router-link>
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
const form = ref({ email: '', code: '', nickname: '', password: '' })
const confirmPassword = ref('')

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

const handleRegister = async () => {
  if (form.value.password.length < 8 || new TextEncoder().encode(form.value.password).length > 72 || !form.value.password.trim()) {
    ElMessage.warning('密码至少 8 位，不能全为空格，且不超过 72 字节')
    return
  }
  if (form.value.password !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  if (!form.value.email || !form.value.code) {
    ElMessage.warning('请填写邮箱和验证码')
    return
  }
  loading.value = true
  try {
    const res = await authApi.register(form.value)
    store.setToken(res.access_token)
    await store.fetchUser()
    ElMessage.success('注册成功')
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
  padding: 36px 32px;
  box-shadow: var(--shadow-hover);
}
.auth-header {
  text-align: center;
  margin-bottom: 28px;
}
.auth-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--ink-darkest);
  letter-spacing: 6px;
}
.auth-header p {
  color: var(--ink-secondary);
  font-size: 14px;
  margin-top: 6px;
}
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
  margin-top: 18px;
  font-size: 14px;
  color: var(--ink-secondary);
}
.auth-footer a {
  color: var(--accent-rose);
  text-decoration: none;
}
</style>
