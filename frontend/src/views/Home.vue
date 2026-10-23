<template>
  <main class="home-page">
    <section class="relationship-hero" :class="{ 'has-cover': !!heroBg }" :style="coverStyle">
      <div v-if="heroBg" class="cover-mask"></div>
      <div class="hero-tools">
        <el-upload :show-file-list="false" :before-upload="handleBgUpload" accept="image/*">
          <button class="quiet-button" title="更换情侣封面"><el-icon><Picture /></el-icon></button>
        </el-upload>
        <button v-if="heroBg" class="quiet-button" title="恢复默认封面" @click="resetBg">
          <el-icon><RefreshLeft /></el-icon>
        </button>
      </div>

      <div class="brand-line"><span class="brand-mark">墨韵</span><span>OUR STORY</span></div>
      <div v-if="couple" class="couple-summary">
        <div class="person">
          <el-avatar :size="54" :src="assetUrl(couple.user1?.avatar)">{{ couple.user1?.nickname?.[0] || '?' }}</el-avatar>
          <span>{{ couple.user1?.nickname || '我' }}</span>
        </div>
        <button class="relationship-days" type="button" aria-label="设置恋爱开始日期" @click="openRelationshipDate">
          <strong>{{ daysTogether ?? '♥' }}</strong>
          <span>{{ daysTogether === null ? '设置恋爱日期' : '天相伴 · 点击修改' }}</span>
          <i>♥</i>
        </button>
        <div class="person">
          <el-avatar :size="54" :src="assetUrl(couple.user2?.avatar)">{{ couple.user2?.nickname?.[0] || '?' }}</el-avatar>
          <span>{{ couple.user2?.nickname || 'Ta' }}</span>
        </div>
      </div>
      <div v-else class="solo-summary">
        <h1>把两个人的故事，慢慢写在一起</h1>
        <p>绑定另一半后，共同记录、共同回忆。</p>
      </div>
      <p class="hero-caption">{{ poem }}</p>
    </section>

    <section v-if="!store.hasCouple" class="bind-notice" @click="go('/bind')">
      <div><strong>邀请另一半加入</strong><p>绑定后即可开启共享记忆和情侣空间</p></div>
      <span>立即绑定</span>
    </section>

    <template v-else>
      <section class="ai-brief" @click="go('/ai/memory')">
        <div class="brief-topline">
          <div class="assistant-sign"><span class="spark">✦</span><span>今日关系简报</span></div>
          <span class="memory-count">{{ memoryTotal }} 条记忆</span>
        </div>
        <h1>{{ briefHeadline }}</h1>
        <ul>
          <li v-for="point in briefPoints.slice(0, 1)" :key="point">{{ point }}</li>
        </ul>
        <div class="brief-footer">
          <span>内容来自你们共同确认的记录</span>
          <button>查看共同记忆 <b>→</b></button>
        </div>
      </section>

      <section class="section important-section">
        <div class="section-heading">
          <div><span class="eyebrow">UP NEXT</span><h2>下一件重要的事</h2></div>
          <button @click="go('/ai/reminders')">全部提醒</button>
        </div>
        <div class="upcoming-card" @click="go('/ai/reminders')">
          <div class="date-block">
            <strong>{{ nextDate.day }}</strong><span>{{ nextDate.month }}</span>
          </div>
          <div class="upcoming-copy">
            <span class="soft-label">{{ nextReminder ? '智能提醒' : '共同计划' }}</span>
            <h3>{{ nextImportantTitle }}</h3>
            <p>{{ nextImportantDescription }}</p>
          </div>
          <div class="countdown"><strong>{{ nextDays }}</strong><span>天后</span></div>
        </div>
      </section>


    </template>

    <el-dialog v-model="dateDialogVisible" title="我们的恋爱开始日" width="min(90vw, 380px)" append-to-body>
      <p class="date-dialog-tip">从真正心动的那一天开始计算，当天计为第 1 天。双方共享这个日期。</p>
      <el-date-picker v-model="relationshipDate" type="date" value-format="YYYY-MM-DD" placeholder="选择开始恋爱的日期" :disabled-date="disableFutureDate" style="width:100%" />
      <template #footer>
        <el-button @click="dateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingDate" :disabled="!relationshipDate" @click="saveRelationshipDate">保存</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Picture, RefreshLeft,
} from '@element-plus/icons-vue'
import {
  aiApi, anniversaryApi, assetUrl, memoryApi, settingsApi,
} from '../api'
import { useUserStore } from '../stores/user'
import { preprocessImage } from '../utils/image'

const router = useRouter()
const store = useUserStore()
const couple = ref(null)
const heroBg = ref('')
const reminders = ref([])
const anniversaries = ref([])
const latestMemory = ref(null)
const memoryTotal = ref(0)
const dateDialogVisible = ref(false)
const relationshipDate = ref('')
const savingDate = ref(false)
const today = ref(new Date())
const disableFutureDate = date => date > new Date()
const openRelationshipDate = () => {
  relationshipDate.value = couple.value?.relationship_start_date || ''
  dateDialogVisible.value = true
}
const saveRelationshipDate = async () => {
  if (!relationshipDate.value || savingDate.value) return
  savingDate.value = true
  try {
    const result = await settingsApi.setRelationshipDate(relationshipDate.value)
    couple.value.relationship_start_date = result.relationship_start_date
    today.value = new Date()
    dateDialogVisible.value = false
    ElMessage.success('已更新你们的恋爱开始日')
  } catch { /* 请求错误由统一拦截器提示 */ }
  finally { savingDate.value = false }
}

const poems = ['愿得一心人，白首不相离', '山有木兮木有枝，心悦君兮君不知', '两情若是久长时，又岂在朝朝暮暮']
const poem = computed(() => poems[new Date().getDate() % poems.length])
const coverStyle = computed(() => heroBg.value ? { backgroundImage: `url(${assetUrl(heroBg.value)})` } : {})
const daysTogether = computed(() => {
  if (!couple.value?.relationship_start_date) return null
  const [year, month, day] = couple.value.relationship_start_date.split('-').map(Number)
  const current = today.value
  const elapsed = Date.UTC(current.getFullYear(), current.getMonth(), current.getDate()) - Date.UTC(year, month - 1, day)
  return Math.max(1, Math.round(elapsed / 86400000) + 1)
})

const nextReminder = computed(() => reminders.value[0] || null)
const nextAnniversary = computed(() => [...anniversaries.value]
  .filter(item => item.days_until !== null)
  .sort((a, b) => a.days_until - b.days_until)[0] || null)
const nextDays = computed(() => nextReminder.value?.days_until ?? nextAnniversary.value?.days_until ?? 0)
const nextImportantTitle = computed(() => nextAnniversary.value?.title || '留一点时间给彼此')
const nextImportantDescription = computed(() => nextReminder.value?.content || nextAnniversary.value?.description || '今天也可以一起记录一个值得记住的瞬间。')
const nextDate = computed(() => {
  const raw = nextReminder.value?.trigger_date || nextAnniversary.value?.date
  if (!raw) return { day: '--', month: '待定' }
  const date = new Date(`${raw}T00:00:00`)
  return { day: String(date.getDate()).padStart(2, '0'), month: `${date.getMonth() + 1} 月` }
})
const briefHeadline = computed(() => {
  if (nextReminder.value && nextDays.value <= 7) return '有一件重要的事，值得提前准备。'
  return '你们最近的故事，正在慢慢连成一条线。'
})
const briefPoints = computed(() => {
  const points = []
  if (nextReminder.value) points.push(nextReminder.value.content)
  if (latestMemory.value) points.push(`最近记录：「${latestMemory.value.title || '新的共同片段'}」`)
  points.push('小助手已结合聊天、日记、相册和纪念日更新共同记忆。')
  return points.slice(0, 3)
})

const go = path => router.push(path)
const handleBgUpload = async file => {
  if (file.size > 50 * 1024 * 1024) { ElMessage.warning('图片不能超过 50MB'); return false }
  try {
    const result = await settingsApi.uploadHeroBg(await preprocessImage(file))
    heroBg.value = result.url
  } catch (error) { ElMessage.error(error?.response?.data?.detail || '背景上传失败') }
  return false
}
const resetBg = async () => {
  await settingsApi.resetHeroBg()
  heroBg.value = ''
}

onMounted(async () => {
  if (!store.hasCouple) return
  const [coupleResult, reminderResult, anniversaryResult, memoryResult, recentChatResult] = await Promise.allSettled([
    settingsApi.coupleInfo(), aiApi.reminders(), anniversaryApi.list(),
    memoryApi.list({ status: 'confirmed', limit: 1 }),
    memoryApi.list({ status: 'confirmed', source_type: 'chat', limit: 1 }),
  ])
  if (coupleResult.status === 'fulfilled') {
    couple.value = coupleResult.value
    heroBg.value = coupleResult.value?.hero_bg || ''
  }
  if (reminderResult.status === 'fulfilled') reminders.value = reminderResult.value
  if (anniversaryResult.status === 'fulfilled') anniversaries.value = anniversaryResult.value
  if (memoryResult.status === 'fulfilled') {
    memoryTotal.value = memoryResult.value.total || 0
  }
  if (recentChatResult.status === 'fulfilled') latestMemory.value = recentChatResult.value.items?.[0] || null
})
</script>

<style scoped>
.home-page { --paper:#f7f4ef; --card:#fffdf9; --ink:#282522; --muted:#7e7770; --rose:#bd6c68; --rose-soft:#f2dfdc; --sage:#778c7c; max-width:720px; min-height:100vh; margin:0 auto; padding:0 18px 104px; color:var(--ink); background:var(--paper); }
.relationship-hero { position:relative; min-height:218px; margin:0 -18px; padding:22px 28px 24px; overflow:hidden; border-radius:0 0 28px 28px; background:linear-gradient(145deg,#eee5dc,#f4dedb 58%,#e5e8df); background-size:cover; background-position:center; }
.relationship-hero::after { content:''; position:absolute; right:-55px; bottom:-75px; width:210px; height:210px; border:1px solid rgba(255,255,255,.45); border-radius:50%; box-shadow:0 0 0 30px rgba(255,255,255,.1),0 0 0 60px rgba(255,255,255,.08); }
.cover-mask { position:absolute; inset:0; background:linear-gradient(180deg,rgba(20,18,17,.25),rgba(20,18,17,.58)); }
.hero-tools { position:absolute; z-index:3; top:18px; right:20px; display:flex; gap:7px; }
.quiet-button { width:30px; height:30px; border:0; border-radius:50%; display:grid; place-items:center; color:#fff; background:rgba(40,37,34,.24); backdrop-filter:blur(8px); cursor:pointer; }
.brand-line { position:relative; z-index:2; display:flex; align-items:center; gap:10px; color:rgba(40,37,34,.55); font-size:9px; letter-spacing:2px; }
.has-cover .brand-line,.has-cover .hero-caption,.has-cover .person span,.has-cover .relationship-days span { color:rgba(255,255,255,.78); }
.brand-mark { color:var(--ink); font-family:serif; font-size:17px; font-weight:700; letter-spacing:5px; }
.has-cover .brand-mark,.has-cover .relationship-days strong { color:#fff; }
.couple-summary { position:relative; z-index:2; display:flex; align-items:center; justify-content:center; gap:28px; margin-top:24px; }
.person { display:flex; flex-direction:column; align-items:center; gap:7px; font-size:12px; font-weight:600; }
.person :deep(.el-avatar) { border:2px solid rgba(255,255,255,.8); color:var(--rose); background:#fff8f5; box-shadow:0 8px 24px rgba(70,45,40,.12); }
.relationship-days { position:relative; min-width:88px; text-align:center; border:0; padding:6px; background:transparent; cursor:pointer; font:inherit; border-radius:12px; }
.relationship-days:focus-visible { outline:2px solid var(--rose); outline-offset:4px; }
.date-dialog-tip { margin-bottom:18px; color:var(--ink-secondary); font-size:13px; line-height:1.8; }
.relationship-days strong { display:block; color:var(--ink); font-family:Georgia,serif; font-size:38px; line-height:1; }
.relationship-days span { display:block; margin-top:4px; color:var(--muted); font-size:10px; letter-spacing:3px; }
.relationship-days i { position:absolute; top:-5px; right:8px; color:var(--rose); font-size:11px; font-style:normal; }
.hero-caption { position:relative; z-index:2; margin:18px 0 0; color:rgba(40,37,34,.55); text-align:center; font-family:serif; font-size:11px; letter-spacing:3px; }
.solo-summary { position:relative; z-index:2; margin:44px 0 30px; }.solo-summary h1{font-family:serif;font-size:23px}.solo-summary p{margin-top:8px;color:var(--muted);font-size:12px}
.bind-notice { margin:18px 0; padding:18px; display:flex; justify-content:space-between; align-items:center; border:1px solid #ead8d4; border-radius:16px; background:var(--card); cursor:pointer; }.bind-notice p{margin-top:4px;color:var(--muted);font-size:12px}.bind-notice>span{color:var(--rose);font-size:13px}
.ai-brief { position:relative; margin-top:18px; padding:21px 21px 18px; overflow:hidden; border-radius:21px; color:#fff; background:linear-gradient(135deg,#392f2d,#57433e); box-shadow:0 14px 38px rgba(57,47,45,.16); cursor:pointer; }
.ai-brief::after { content:'AI'; position:absolute; right:-5px; bottom:-28px; color:rgba(255,255,255,.035); font:700 110px/1 Georgia,serif; }
.brief-topline,.brief-footer { position:relative; z-index:1; display:flex; align-items:center; justify-content:space-between; }
.assistant-sign { display:flex; align-items:center; gap:7px; font-size:12px; letter-spacing:1px; }.spark{color:#e7b7af;font-size:16px}.memory-count{padding:4px 9px;border:1px solid rgba(255,255,255,.15);border-radius:999px;color:rgba(255,255,255,.7);font-size:10px}
.ai-brief h1 { position:relative; z-index:1; margin:17px 0 12px; max-width:480px; font-family:serif; font-size:22px; font-weight:600; letter-spacing:1px; }
.ai-brief ul { position:relative; z-index:1; margin:0; padding:0; list-style:none; }.ai-brief li{margin:7px 0;color:rgba(255,255,255,.78);font-size:12px;line-height:1.55}.ai-brief li::before{content:'—';margin-right:8px;color:#dca29c}
.brief-footer { margin-top:17px; padding-top:14px; border-top:1px solid rgba(255,255,255,.1); }.brief-footer>span{color:rgba(255,255,255,.42);font-size:9px}.brief-footer button{border:0;color:#fff;background:none;font-size:11px;cursor:pointer}.brief-footer b{margin-left:4px;color:#e7b7af}
.section { margin-top:31px; }.section-heading{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:13px}.section-heading h2{margin:2px 0 0;font-family:serif;font-size:19px;letter-spacing:1px}.eyebrow{color:var(--rose);font-size:8px;font-weight:700;letter-spacing:2px}.section-heading button{border:0;color:var(--muted);background:none;font-size:11px;cursor:pointer}.section-note{max-width:220px;color:var(--muted);font-size:9px;text-align:right}
.upcoming-card { display:flex;align-items:center;gap:15px;padding:17px;border:1px solid #e9e1da;border-radius:18px;background:var(--card);cursor:pointer;box-shadow:0 7px 24px rgba(70,55,45,.045); }
.date-block{width:54px;height:59px;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:13px;color:var(--rose);background:var(--rose-soft)}.date-block strong{font:700 23px/1 Georgia,serif}.date-block span{margin-top:4px;font-size:9px;letter-spacing:1px}
.upcoming-copy{flex:1;min-width:0}.soft-label{color:var(--sage);font-size:9px;letter-spacing:1px}.upcoming-copy h3{margin:4px 0;font-size:14px}.upcoming-copy p{overflow:hidden;color:var(--muted);font-size:10px;white-space:nowrap;text-overflow:ellipsis}.countdown{padding-left:12px;border-left:1px solid #eee5dd;text-align:center}.countdown strong{display:block;color:var(--rose);font:700 20px/1 Georgia,serif}.countdown span{color:var(--muted);font-size:9px}
@media(max-width:480px){.home-page{padding-left:14px;padding-right:14px}.relationship-hero{margin-left:-14px;margin-right:-14px}.section-note{display:none}.couple-summary{gap:20px}.ai-brief h1{font-size:19px}.brief-footer>span{display:none}}
.home-page{min-height:0;padding-bottom:24px}
</style>
