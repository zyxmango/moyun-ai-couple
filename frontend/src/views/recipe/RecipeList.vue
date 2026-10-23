<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">情侣菜谱</h2>
      <el-button type="primary" size="small" @click="openCreate">添加菜谱</el-button>
    </div>

    <!-- 分类筛选 -->
    <div class="filter-bar">
      <div class="filter-group">
        <span
          v-for="c in categories"
          :key="c.value"
          class="filter-tag"
          :class="{ active: filter.category === c.value }"
          @click="setCategory(c.value)"
        >{{ c.label }}</span>
      </div>
      <div class="filter-group sub">
        <span
          v-for="c in chefFilters"
          :key="c.value"
          class="filter-tag sm"
          :class="{ active: filter.chef === c.value }"
          @click="setChef(c.value)"
        >{{ c.label }}</span>
      </div>
    </div>

    <!-- 随机推荐 -->
    <div v-if="randomRecipe" class="random-card ink-card" @click="goDetail(randomRecipe.id)">
      <div class="random-label">💡 今天吃这个？</div>
      <div class="random-info">
        <span class="random-title">{{ randomRecipe.title }}</span>
        <el-button text size="small" @click.stop="loadRandom">换一个</el-button>
      </div>
    </div>

    <!-- 菜谱列表 -->
    <div v-if="list.length === 0" class="empty">还没有菜谱，添加第一道吧 ♥</div>

    <div class="recipe-grid">
      <div
        v-for="r in list"
        :key="r.id"
        class="recipe-card"
        @click="goDetail(r.id)"
      >
        <div class="cover-wrap">
          <img v-if="r.cover" :src="assetUrl(r.cover)" class="cover" />
          <div v-else class="cover-placeholder">🍽️</div>
          <span v-if="r.want_eat" class="want-badge">想吃</span>
        </div>
        <div class="info">
          <div class="title-row">
            <span class="title">{{ r.title }}</span>
            <span class="diff" :class="r.difficulty">{{ diffMap[r.difficulty] }}</span>
          </div>
          <div class="meta">🍳 {{ r.cook_time }}分钟 · 做{{ r.cook_count }}次</div>
          <div class="bottom">
            <span class="score">❤ {{ r.avg_score || '暂无' }}</span>
            <span class="chef">{{ r.chef_nickname || '未定' }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑弹窗 -->
    <el-dialog v-model="showDialog" :title="editId ? '编辑菜谱' : '添加菜谱'" width="92%" top="5vh">
      <el-form :model="form" label-position="top">
        <el-form-item label="菜名">
          <el-input v-model="form.title" placeholder="如：番茄炒蛋" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="分类" class="flex1">
            <el-select v-model="form.category" style="width:100%">
              <el-option v-for="c in categories.filter(x => x.value)" :key="c.value" :label="c.label" :value="c.value" />
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
            <el-radio :label="store.user?.id">{{ store.user?.nickname || '我' }}</el-radio>
            <el-radio v-if="partner" :label="partner.id">{{ partner.nickname }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="封面图">
          <el-upload
            :show-file-list="false"
            :before-upload="handleCover"
            accept="image/*"
          >
            <img v-if="form.cover" :src="assetUrl(form.cover)" class="cover-preview" />
            <el-button v-else size="small">点击上传封面</el-button>
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
              <el-input v-model="form.steps[i]" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="这一步..." />
              <el-button text type="danger" @click="form.steps.splice(i, 1)">×</el-button>
            </div>
            <el-button size="small" @click="form.steps.push('')">+ 添加步骤</el-button>
          </div>
        </el-form-item>
        <el-form-item>
          <el-switch v-model="form.want_eat" active-text="加入想吃清单" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { recipeApi, settingsApi, assetUrl } from '../../api'
import { useUserStore } from '../../stores/user'
import { preprocessImage } from '../../utils/image'

const router = useRouter()
const store = useUserStore()
const list = ref([])
const randomRecipe = ref(null)
const showDialog = ref(false)
const editId = ref(null)
const saving = ref(false)
const partner = ref(null)

const categories = [
  { value: '', label: '全部' },
  { value: 'breakfast', label: '早餐' },
  { value: 'lunch', label: '午餐' },
  { value: 'dinner', label: '晚餐' },
  { value: 'dessert', label: '甜品' },
  { value: 'snack', label: '小食' },
  { value: 'drink', label: '饮品' },
]
const chefFilters = [
  { value: '', label: '全部' },
  { value: 'me', label: '我做的' },
  { value: 'partner', label: 'Ta做的' },
  { value: 'want_eat', label: '想吃' },
]
const diffMap = { easy: '简单', medium: '中等', hard: '困难' }

const filter = reactive({ category: '', chef: '' })

const form = ref({
  title: '', cover: '', category: 'dinner', difficulty: 'easy',
  cook_time: 30, chef_id: null, ingredients: [], steps: [], want_eat: false,
})

const setCategory = (v) => { filter.category = v; load() }
const setChef = (v) => { filter.chef = v; load() }

const load = async () => {
  try {
    list.value = await recipeApi.list({
      category: filter.category || undefined,
      chef: filter.chef || undefined,
    })
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载失败')
  }
}

const loadRandom = async () => {
  try {
    randomRecipe.value = await recipeApi.random()
  } catch {
    randomRecipe.value = null
  }
}

const loadPartner = async () => {
  try {
    const info = await settingsApi.coupleInfo()
    partner.value = info.is_user1 ? info.user2 : info.user1
  } catch {}
}

const goDetail = (id) => router.push(`/recipe/${id}`)

const openCreate = () => {
  editId.value = null
  form.value = {
    title: '', cover: '', category: 'dinner', difficulty: 'easy',
    cook_time: 30, chef_id: store.user?.id, ingredients: [], steps: [], want_eat: false,
  }
  showDialog.value = true
}

const openEdit = (r) => {
  editId.value = r.id
  form.value = {
    title: r.title, cover: r.cover, category: r.category, difficulty: r.difficulty,
    cook_time: r.cook_time, chef_id: r.chef_id || store.user?.id,
    ingredients: r.ingredients?.length ? r.ingredients : [],
    steps: r.steps?.length ? r.steps : [],
    want_eat: r.want_eat,
  }
  showDialog.value = true
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

const save = async () => {
  if (!form.value.title.trim()) {
    ElMessage.warning('请输入菜名')
    return
  }
  // 过滤空食材和空步骤
  const ingredients = form.value.ingredients.filter(i => i.name.trim())
  const steps = form.value.steps.filter(s => s.trim())
  saving.value = true
  try {
    const payload = { ...form.value, ingredients, steps }
    if (editId.value) {
      await recipeApi.update(editId.value, payload)
      ElMessage.success('已更新')
    } else {
      await recipeApi.create(payload)
      ElMessage.success('已添加')
    }
    showDialog.value = false
    load()
    loadRandom()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  load()
  loadRandom()
  loadPartner()
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.filter-bar {
  margin-bottom: 16px;
}
.filter-group {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.filter-group.sub {
  margin-top: 8px;
}
.filter-tag {
  flex-shrink: 0;
  padding: 5px 14px;
  border-radius: 16px;
  background: var(--bg-card);
  font-size: 13px;
  color: var(--ink-secondary);
  cursor: pointer;
  border: 1px solid var(--border-soft);
  transition: all 0.2s;
}
.filter-tag.sm {
  font-size: 12px;
  padding: 4px 12px;
}
.filter-tag.active {
  background: var(--accent-rose);
  color: #fff;
  border-color: var(--accent-rose);
}
.random-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 14px 18px;
  cursor: pointer;
  border-left: 3px solid var(--accent-gold);
}
.random-label {
  font-size: 13px;
  color: var(--ink-secondary);
}
.random-info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.random-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--ink-darkest);
}
.empty {
  text-align: center;
  color: var(--ink-light);
  margin-top: 30%;
  font-size: 15px;
}
.recipe-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.recipe-card {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
  cursor: pointer;
  transition: transform 0.3s, box-shadow 0.3s;
}
.recipe-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-hover);
}
.cover-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  background: var(--bg-soft);
}
.cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
}
.want-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--accent-rose);
  color: #fff;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
}
.info {
  padding: 10px 12px 12px;
}
.title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-darkest);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.diff {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
}
.diff.easy { background: #eef5f2; color: #5e8b7e; }
.diff.medium { background: #faf5ec; color: #c9a96e; }
.diff.hard { background: #faf0f0; color: #c96b6b; }
.meta {
  font-size: 11px;
  color: var(--ink-light);
  margin-bottom: 6px;
}
.bottom {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}
.score { color: var(--accent-rose); }
.chef { color: var(--ink-secondary); }

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
.ingredients, .steps {
  width: 100%;
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

@media (max-width: 480px) {
  .recipe-grid {
    gap: 10px;
  }
  .info {
    padding: 8px 10px 10px;
  }
  .title {
    font-size: 13px;
  }
}
</style>
