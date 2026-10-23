<template>
  <main class="reset-page">
    <section class="reset-card">
      <h1>设置 / 重置密码</h1>
      <p class="intro">忘记密码或还没设置过密码？验证邮箱后即可设置。</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="邮箱"><el-input v-model="form.email" type="email" autocomplete="email" placeholder="注册时使用的邮箱" /></el-form-item>
        <el-form-item label="邮箱验证码">
          <div class="code-row"><el-input v-model="form.code" maxlength="6" inputmode="numeric" autocomplete="one-time-code" placeholder="6 位验证码" /><el-button :disabled="countdown > 0" :loading="sending" @click="sendCode">{{ countdown ? `${countdown}s` : '获取验证码' }}</el-button></div>
        </el-form-item>
        <el-form-item label="新密码"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" placeholder="至少 8 位" /></el-form-item>
        <el-form-item label="确认密码"><el-input v-model="confirmation" type="password" show-password autocomplete="new-password" placeholder="再次输入新密码" /></el-form-item>
        <el-button class="submit-button" type="primary" native-type="submit" :loading="saving">保存新密码</el-button>
      </el-form>
      <p class="footnote">保存后请重新登录。聊天与情侣关系不会改变。</p>
      <router-link class="back" :to="store.isLoggedIn ? '/settings' : '/login'">{{ store.isLoggedIn ? '返回我的' : '返回登录' }}</router-link>
    </section>
  </main>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi } from '../../api'
import { useUserStore } from '../../stores/user'

const store = useUserStore()
const route = useRoute()
const router = useRouter()
const form = ref({ email: store.user?.email?.trim() || String(route.query.email || ''), code: '', password: '' })
const confirmation = ref('')
const countdown = ref(0)
const sending = ref(false)
const saving = ref(false)
let timer
const sendCode = async () => {
  if (sending.value || countdown.value) return
  if (!form.value.email.trim()) return ElMessage.warning('请输入注册邮箱')
  sending.value = true
  try {
    const result = await authApi.sendCode(form.value.email.trim(), 'reset_password')
    if (result.code) {
      form.value.code = result.code
      ElMessage.warning('本地测试验证码已填入')
    } else ElMessage.success('验证码已发送，请查收邮箱')
    countdown.value = 60
    timer = setInterval(() => { if (--countdown.value <= 0) clearInterval(timer) }, 1000)
  } catch { /* 统一接口错误提示 */ }
  finally { sending.value = false }
}
const submit = async () => {
  if (saving.value) return
  if (!form.value.email.trim() || !form.value.code.trim()) return ElMessage.warning('请填写邮箱和验证码')
  if (form.value.password.length < 8 || new TextEncoder().encode(form.value.password).length > 72 || !form.value.password.trim()) return ElMessage.warning('密码至少 8 位，不能全为空格，且不超过 72 字节')
  if (form.value.password !== confirmation.value) return ElMessage.warning('两次输入的密码不一致')
  saving.value = true
  try {
    await authApi.resetPassword({ ...form.value, email: form.value.email.trim(), code: form.value.code.trim() })
    store.logout()
    ElMessage.success('密码已更新，请使用新密码登录')
    router.replace('/login')
  } catch { /* 统一接口错误提示 */ }
  finally { saving.value = false }
}
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.reset-page{min-height:100dvh;display:flex;align-items:center;justify-content:center;padding:24px 18px;background:linear-gradient(135deg,var(--bg-paper),var(--accent-rose-bg))}
.reset-card{width:100%;max-width:400px;padding:30px 24px;border-radius:20px;background:var(--bg-card);box-shadow:var(--shadow-soft)}
h1{font-size:23px;text-align:center}.intro{margin:12px 0 26px;font-size:13px;line-height:1.8;color:var(--ink-secondary)}
.code-row{display:flex;gap:8px;width:100%}.code-row .el-input{min-width:0;flex:1}.submit-button{width:100%;height:42px;margin-top:8px}
.footnote{font-size:12px;line-height:1.8;color:var(--ink-secondary);margin:16px 0}.back{display:block;text-align:center;color:var(--accent-rose);font-size:13px;text-decoration:none}
</style>
