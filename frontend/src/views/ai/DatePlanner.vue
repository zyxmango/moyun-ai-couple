<template>
  <div class="page-container planner-page">
    <header class="planner-head">
      <div class="eyebrow">MEMORY-AWARE DATE AGENT</div>
      <h2>智能约会规划</h2>
      <p>综合双方共享记忆与你可见的个人偏好，生成有依据、可调整的约会方案。</p>
    </header>

    <div class="planner-layout">
      <section class="ink-card plan-form">
        <h3>这次想怎么约会？</h3>
        <el-form label-position="top">
          <div class="form-grid">
            <el-form-item label="城市"><el-input v-model="form.city" placeholder="例如：成都" /></el-form-item>
            <el-form-item label="日期"><el-input v-model="form.desired_date" placeholder="例如：本周六下午" /></el-form-item>
            <el-form-item label="预算"><el-input v-model="form.budget" placeholder="例如：两人 300 元内" /></el-form-item>
            <el-form-item label="时长">
              <el-select v-model="form.duration"><el-option label="2 小时" value="2小时" /><el-option label="半天" value="半天" /><el-option label="一天" value="一天" /></el-select>
            </el-form-item>
          </div>
          <el-form-item label="这次特别想做什么"><el-input v-model="form.preferences" type="textarea" :rows="3" placeholder="安静一点、想看展、想吃甜品……" /></el-form-item>
          <el-form-item label="需要避开什么"><el-input v-model="form.avoid" placeholder="例如：少辣、不走太远、避免人多" /></el-form-item>
          <el-button type="primary" class="generate-btn" :loading="generating" @click="generate">结合我们的记忆生成方案</el-button>
        </el-form>
        <div class="safe-note">只检索你当前有权查看的记忆；不会向另一方展示你的私密内容。</div>
      </section>

      <section class="ink-card result-card">
        <template v-if="current">
          <div class="result-meta"><span>方案 #{{ current.id }}</span><span>参考 {{ current.sources.length }} 条记忆</span></div>
          <div class="plan-content">{{ current.content }}</div>
          <div v-if="current.sources.length" class="evidence">
            <h4>本次规划依据</h4>
            <div v-for="(item, index) in current.sources.slice(0, 5)" :key="item.id" class="evidence-item">
              <b>[{{ index + 1 }}] {{ item.title }}</b>
              <span>{{ item.visibility === 'private' ? '仅自己可见' : '双方共享' }} · {{ item.content }}</span>
            </div>
          </div>
        </template>
        <div v-else class="empty-result">
          <div class="empty-mark">✦</div>
          <h3>方案会出现在这里</h3>
          <p>信息不需要填满；记录过的偏好越多，规划就越贴合你们。</p>
        </div>
      </section>
    </div>

    <section v-if="history.length" class="history-section">
      <h3>最近方案</h3>
      <div class="history-list">
        <button v-for="item in history" :key="item.id" @click="current = item">
          <b>{{ item.city || '未指定城市' }} · {{ item.duration }}</b>
          <span>{{ item.desired_date || new Date(item.created_at).toLocaleDateString('zh-CN') }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { datePlanApi } from '../../api'

const generating = ref(false)
const current = ref(null)
const history = ref([])
const form = reactive({ city: '', desired_date: '', budget: '', duration: '半天', preferences: '', avoid: '' })

const loadHistory = async () => {
  const result = await datePlanApi.history(8)
  history.value = result.items
}

const generate = async () => {
  if (!form.city.trim() && !form.preferences.trim()) return ElMessage.warning('至少填写城市或本次偏好')
  generating.value = true
  try {
    current.value = await datePlanApi.create({ ...form })
    await loadHistory()
    ElMessage.success('已生成一份基于可见记忆的约会方案')
  } finally { generating.value = false }
}

onMounted(loadHistory)
</script>

<style scoped>
.planner-page { max-width:980px; }
.planner-head { margin-bottom:22px; }
.eyebrow { color:var(--accent-rose); font-size:10px; letter-spacing:2px; font-weight:700; }
.planner-head h2 { margin:7px 0 5px; font-size:26px; color:var(--ink-darkest); }
.planner-head p { margin:0; color:var(--ink-secondary); font-size:13px; }
.planner-layout { display:grid; grid-template-columns:minmax(320px, .8fr) minmax(360px, 1.2fr); gap:16px; align-items:start; }
.plan-form,.result-card { padding:24px; }
.plan-form h3 { margin:0 0 18px; }
.form-grid { display:grid; grid-template-columns:1fr 1fr; gap:0 12px; }
.form-grid :deep(.el-select) { width:100%; }
.generate-btn { width:100%; height:42px; }
.safe-note { margin-top:14px; color:var(--ink-light); font-size:11px; line-height:1.6; text-align:center; }
.result-card { min-height:440px; }
.result-meta { display:flex; justify-content:space-between; color:var(--ink-light); font-size:11px; border-bottom:1px solid var(--border-soft); padding-bottom:12px; }
.plan-content { white-space:pre-wrap; line-height:1.9; color:var(--ink-primary); font-size:13px; padding:18px 0; }
.evidence { border-top:1px solid var(--border-soft); padding-top:14px; }
.evidence h4 { margin:0 0 10px; }
.evidence-item { padding:10px 12px; background:var(--bg-soft); border-radius:10px; margin-bottom:8px; }
.evidence-item b,.evidence-item span { display:block; font-size:11px; }
.evidence-item span { color:var(--ink-secondary); margin-top:4px; line-height:1.5; }
.empty-result { min-height:390px; display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; color:var(--ink-secondary); }
.empty-mark { font-size:36px; color:var(--accent-rose); }.empty-result h3 { color:var(--ink-darkest); margin:12px 0 4px; }.empty-result p { max-width:280px; font-size:12px; line-height:1.7; }
.history-section { margin-top:26px; }.history-section h3 { font-size:15px; }
.history-list { display:flex; gap:10px; overflow:auto; padding-bottom:6px; }
.history-list button { min-width:170px; text-align:left; border:1px solid var(--border-soft); background:var(--bg-card); border-radius:12px; padding:12px; cursor:pointer; }
.history-list b,.history-list span { display:block; }.history-list b { color:var(--ink-darkest); }.history-list span { margin-top:4px; color:var(--ink-light); font-size:11px; }
@media (max-width:760px) { .planner-layout { grid-template-columns:1fr; }.result-card { min-height:300px; }.form-grid { grid-template-columns:1fr; } }
</style>
