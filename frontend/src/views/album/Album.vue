<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">共享相册</h2>
      <el-upload :show-file-list="false" :before-upload="upload" accept="image/*">
        <el-button type="primary" size="small" :loading="uploading">上传</el-button>
      </el-upload>
    </div>

    <div v-if="photos.length === 0" class="empty">还没有照片，上传你们的美好瞬间</div>

    <div class="photo-grid">
      <div v-for="p in photos" :key="p.id" class="photo-item">
        <el-image :src="assetUrl(p.url)" fit="cover" :preview-src-list="previewList" :initial-index="photos.indexOf(p)" class="photo-img" lazy />
        <div class="photo-info">
          <span class="uploader">{{ p.uploader_nickname }}</span>
          <el-button text size="small" type="danger" @click="del(p)">删除</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { albumApi, assetUrl } from '../../api'

const photos = ref([])
const uploading = ref(false)
const previewList = computed(() => photos.value.map((p) => assetUrl(p.url)))

const load = async () => {
  try {
    photos.value = await albumApi.list()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (detail && detail.includes('尚未绑定')) return
    ElMessage.error(detail || '加载相册失败')
  }
}

const upload = async (file) => {
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.warning('单张图片不能超过 20MB')
    return false
  }
  uploading.value = true
  try {
    await albumApi.upload(file)
    ElMessage.success('上传成功')
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
  return false
}

const del = async (p) => {
  try {
    await ElMessageBox.confirm('确定删除这张照片？', '提示')
  } catch { return }
  try {
    await albumApi.delete(p.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.empty {
  text-align: center;
  color: var(--ink-light);
  margin-top: 40%;
  font-size: 15px;
}
.photo-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-top: 12px;
}
.photo-item {
  background: var(--bg-card);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-soft);
}
.photo-img {
  width: 100%;
  aspect-ratio: 1;
  display: block;
}
.photo-info {
  padding: 6px 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.uploader {
  font-size: 12px;
  color: var(--ink-secondary);
}
</style>
