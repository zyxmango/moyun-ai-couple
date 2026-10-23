<template>
  <div class="detail-page" v-if="recipe">
    <!-- 顶部返回 -->
    <div class="top-bar">
      <el-button text @click="goBack"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
      <div class="actions">
        <el-button text size="small" @click="openEdit">编辑</el-button>
        <el-button text size="small" type="danger" @click="remove">删除</el-button>
      </div>
    </div>

    <!-- 封面 -->
    <div class="cover-block">
      <img v-if="recipe.cover" :src="recipe.cover" class="cover" />
      <div v-else class="cover-default">🍽️</div>
    </div>

    <!-- 标题 -->
    <div class="head">
      <h1 class="title">{{ recipe.title }}</h1>
      <div class="tags">
        <span class="tag">{{ catMap[recipe.category] }}</span>
        <span class="tag" :class="recipe.difficulty">{{ diffMap[recipe.difficulty] }}</span>
        <span class="tag">🍳 {{ recipe.cook_time }}分钟</span>
      </div>
      <div class="chef-line">
        <el-avatar :size="26" :src="''">{{ recipe.chef_nickname?.[0] || '?' }}</el-avatar>
        <span>{{ recipe.chef_nickname || '未指定' }} · 做过 {{ recipe.cook_count }} 次</span>
      </div>
    </div>

    <!-- 食材 -->
    <section class="block" v-if="recipe.ingredients?.length">
      <h3 class="block-title">🥗 食材清单</h3>
      <ul class="ingredients">
        <li v-for="(ing, i) in recipe.ingredients" :key="i">
          <span class="ing-name">{{ ing.name }}</span>
          <span class="ing-amount">{{ ing.amount }}</span>
        </li>
      </ul>
    </section>

    <!-- 步骤 -->
    <section class="block" v-if="recipe.steps?.length">
      <h3 class="block-title">📝 烹饪步骤</h3>
      <ol class="steps">
        <li v-for="(step, i) in recipe.steps" :key="i">
          <div class="step-num">{{ i + 1 }}</div>
          <div class="step-text">{{ step }}</div>
        </li>
      </ol>
    </section>

    <!-- 评分 -->
    <section class="block">
      <h3 class="block-title">❤ 爱心评分</h3>
      <div class="rate-block">
        <div class="avg">
          <span class="big">{{ recipe.avg_score || '0.0' }}</span>
          <span class="label">/ 5.0</span>
        </div>
        <div class="my-rate">
          <span class="my-label">我评：</span>
          <el-rate
            v-model="myScore"
            :max="5"
            :colors="['#c96b6b', '#c96b6b', '#c96b6b']"
            @change="onRate"
          />
        </div>
      </div>
    </section>

    <!-- 留言 -->
    <section class="block">
      <h3 class="block-title">💬 留言区 ({{ comments.length }})</h3>
      <div class="comment-input">
        <el-input v-model="newComment" placeholder="留下你的感想..." @keyup.enter="addComment" />
        <el-button type="primary" size="small" @click="addComment">发送</el-button>
      </div>
      <div class="comments">
        <div v-for="c in comments" :key="c.id" class="comment">
          <el-avatar :size="28">{{ c.user_nickname?.[0] || '?' }}</el-avatar>
          <div class="comment-body">
            <div class="comment-head">
              <span class="comment-name">{{ c.user_nickname }}</span>
              <span class="comment-time">{{ formatTime(c.created_at) }}</span>
              <el-button v-if="c.user_id === userId" text size="small" type="danger" @click="delComment(c.id)">删除</el-button>
            </div>
            <div class="comment-text">{{ c.content }}</div>
          </div>
        </div>
        <div v-if="comments.length === 0" class="empty-c">还没有留言</div>
      </div>
    </section>

    <!-- 底部操作 -->
    <div class="bottom-bar">
      <el-button :type="recipe.want_eat ? 'warning' : 'default'" @click="toggleWant">
        {{ recipe.want_eat ? '✓ 想吃' : '+ 想吃' }}
      </el-button>
      <el-button type="primary" @click="recordCook">🍳 记录这次烹饪</el-button>
    </div>

    <!-- 编辑弹窗复用 -->
    <el-dialog v-model="showEdit" title="编辑菜谱" width="92%" top="5vh">
      <el-form :model="form" label-position="top">
        <el-form-item label="菜名">
          <el-input v-model="form.title" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类" class="flex1">
            <el-select v-model="form.category" style="width:100%">
              <el-option label="早餐" value="breakfast" />
              <el-option label="午餐" value="lunch" />
              <el-option label="晚餐" value="dinner" />
              <el-option label="甜品" value="dessert" />
              <el-option label="小食" value="snack" />
              <el-option label="饮品" value="drink" />
            </el-select>
          </el-form-item>
          <el-form-item label="难度" class="flex1">
            <el-select v-model="form.difficulty" style="width:100%">
              <el-option label="简单" value="easy" />
              <el-option label="中等" value="medium" />
              <el-option label="困难" value="hard" />
            </el-select>
          </el-form-item>
          <el-form-item label="时长(分钟)" class="flex1">
            <el-input-number v-model="form.cook_time" :min="1" :max="600" style="width:100%" />
          </el-form-item>
        </div>
        <el-form-item label="谁做的">
          <el-radio-group v-model="form.chef_id">
            <el-radio :label="userId">{{ store.user?.nickname || '我' }}</el-radio>
            <el-radio v-if="partner" :label="partner.id">{{ partner.nickname }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="封面图">
          <el-upload :show-file-list="false" :before-upload="handleCover" accept="image/*">
            <img v-if="form.cover" :src="form.cover" class="cover-preview" />
            <el-button v-else size="small">上传封面</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="食材清单">
          <div class="ingredients">
            <div v-for="(ing, i) in form.ingredients" :key="i" class="ing-row">
              <el-input v-model="ing.name" placeholder="食材名" class="ing-name" />
              <el-input v-model="ing.amount" placeholder="用量" class="ing-amount" />
              <el-button text type="danger" @click="form.ingredients.splice(i, 1)">×</el-button>
            </div>
            <el-button size="small" @click="form.ingredients.push({ name: '', amount: '' })">+ 添加食材</el-button>
          </div>
        </el-form-item>
        <el-form-item label="烹饪步骤">
          <div class="steps">
            <div v-for="(step, i) in form.steps" :key="i" class="step-row">
              <span class="step-num">{{ i + 1 }}.</span>
              <el-input v-model="form.steps[i]" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              <el-button text type="danger" @click="form.steps.splice(i, 1)">×</el-button>
            </div>
            <el-button size="small" @click="form.steps.push('')">+ 添加步骤</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { recipeApi, settingsApi } from '../../api'
import { useUserStore } from '../../stores/user'
import { preprocessImage } from '../../utils/image'

const router = useRouter()
const route = useRoute()
const store = useUserStore()
const recipe = ref(null)
const comments = ref([])
const myScore = ref(0)
const newComment = ref('')
const showEdit = ref(false)
const saving = ref(false)
const partner = ref(null)

const catMap = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐',
  dessert: '甜品', snack: '小食', drink: '饮品',
}
const diffMap = { easy: '简单', medium: '中等', hard: '困难' }

const userId = computed(() => store.user?.id)

const goBack = () => router.push('/recipe')

const formatTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return d.toLocaleDateString()
}

const load = async () => {
  try {
    recipe.value = await recipeApi.get(route.params.id)
    myScore.value = recipe.value.my_score || 0
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
    goBack()
  }
}

const loadComments = async () => {
  try {
    comments.value = await recipeApi.comments(route.params.id)
  } catch {}
}

const onRate = async (v) => {
  try {
    recipe.value = await recipeApi.rate(route.params.id, v)
    ElMessage.success('评分成功')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '评分失败')
  }
}

const addComment = async () => {
  if (!newComment.value.trim()) return
  try {
    await recipeApi.addComment(route.params.id, newComment.value)
    newComment.value = ''
    loadComments()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '发送失败')
  }
}

const delComment = async (cid) => {
  try {
    await recipeApi.deleteComment(route.params.id, cid)
    loadComments()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

const toggleWant = async () => {
  try {
    await recipeApi.toggleWantEat(route.params.id)
    recipe.value.want_eat = !recipe.value.want_eat
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  }
}

const recordCook = async () => {
  try {
    const res = await recipeApi.cook(route.params.id)
    ElMessage.success(res.message)
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '记录失败')
  }
}

const remove = async () => {
  try {
    await ElMessageBox.confirm('确定删除这道菜谱？', '提示', { type: 'warning' })
    await recipeApi.delete(route.params.id)
    ElMessage.success('已删除')
    goBack()
  } catch {}
}

const form = ref({})
const openEdit = () => {
  form.value = {
    title: recipe.value.title, cover: recipe.value.cover,
    category: recipe.value.category, difficulty: recipe.value.difficulty,
    cook_time: recipe.value.cook_time,
    chef_id: recipe.value.chef_id || userId.value,
    ingredients: recipe.value.ingredients?.length ? recipe.value.ingredients : [],
    steps: recipe.value.steps?.length ? recipe.value.steps : [],
    want_eat: recipe.value.want_eat,
  }
  showEdit.value = true
}

const handleCover = async (file) => {
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.warning('图片不能超过 50MB')
    return false
  }
  try {
    const processed = await preprocessImage(file)
    const res = await recipeApi.uploadCover(processed)
    form.value.cover = res.url
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
  return false
}

const saveEdit = async () => {
  if (!form.value.title.trim()) {
    ElMessage.warning('请输入菜名')
    return
  }
  const ingredients = form.value.ingredients.filter(i => i.name.trim())
  const steps = form.value.steps.filter(s => s.trim())
  saving.value = true
  try {
    recipe.value = await recipeApi.update(route.params.id, { ...form.value, ingredients, steps })
    showEdit.value = false
    ElMessage.success('已更新')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const loadPartner = async () => {
  try {
    const info = await settingsApi.coupleInfo()
    partner.value = info.is_user1 ? info.user2 : info.user1
  } catch {}
}

onMounted(() => {
  load()
  loadComments()
  loadPartner()
})
</script>

<style scoped>
.detail-page {
  padding-bottom: 70px;
}
.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.cover-block {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: var(--radius-md);
  overflow: hidden;
  margin-bottom: 16px;
  background: var(--bg-soft);
}
.cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cover-default {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64px;
}
.head {
  margin-bottom: 20px;
}
.title {
  font-size: 22px;
  font-weight: 700;
  color: var(--ink-darkest);
  margin: 0 0 10px;
}
.tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.tag {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 12px;
  background: var(--bg-soft);
  color: var(--ink-secondary);
}
.tag.easy { background: #eef5f2; color: #5e8b7e; }
.tag.medium { background: #faf5ec; color: #c9a96e; }
.tag.hard { background: #faf0f0; color: #c96b6b; }
.chef-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ink-secondary);
}
.block {
  margin-bottom: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--border-soft);
}
.block-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 12px;
  color: var(--ink-darkest);
}
.ingredients {
  list-style: none;
  padding: 0;
  margin: 0;
}
.ingredients li {
  display: flex;
  justify-content: space-between;
  padding: 9px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-soft);
  margin-bottom: 6px;
  font-size: 13px;
}
.ing-name { color: var(--ink-darkest); }
.ing-amount { color: var(--ink-secondary); }

.steps {
  list-style: none;
  padding: 0;
  margin: 0;
}
.steps li {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}
.step-num {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-rose);
  color: #fff;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.step-text {
  flex: 1;
  font-size: 14px;
  color: var(--ink-darkest);
  line-height: 1.7;
  padding-top: 3px;
}

.rate-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.avg .big {
  font-size: 32px;
  font-weight: 700;
  color: var(--accent-rose);
}
.avg .label {
  font-size: 13px;
  color: var(--ink-light);
}
.my-rate {
  display: flex;
  align-items: center;
  gap: 8px;
}
.my-label {
  font-size: 13px;
  color: var(--ink-secondary);
}

.comment-input {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.comments {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.comment {
  display: flex;
  gap: 10px;
}
.comment-body {
  flex: 1;
}
.comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.comment-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.comment-time {
  font-size: 11px;
  color: var(--ink-light);
}
.comment-text {
  font-size: 14px;
  color: var(--ink-darkest);
  margin-top: 3px;
  line-height: 1.6;
}
.empty-c {
  text-align: center;
  color: var(--ink-light);
  font-size: 13px;
  padding: 16px;
}

.bottom-bar {
  position: fixed;
  bottom: 56px;
  left: 0;
  right: 0;
  display: flex;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg-card);
  box-shadow: 0 -2px 12px rgba(0,0,0,0.06);
  z-index: 10;
  max-width: 720px;
  margin: 0 auto;
}
.bottom-bar .el-button {
  flex: 1;
}

/* 表单 */
.form-row {
  display: flex;
  gap: 10px;
}
.flex1 { flex: 1; }
.cover-preview {
  width: 100%;
  max-height: 160px;
  object-fit: cover;
  border-radius: var(--radius-sm);
}
.ing-row, .step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ing-name { flex: 2; }
.ing-amount { flex: 1; }
.step-num {
  flex-shrink: 0;
  color: var(--accent-rose);
  font-weight: 600;
  width: 24px;
}
.loading {
  text-align: center;
  padding: 60px 0;
  color: var(--ink-light);
}
</style>
