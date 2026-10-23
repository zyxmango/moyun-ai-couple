/**
 * 图片上传前预处理
 * - 自动压缩超大图片
 * - 把任意格式（含 HEIC/HEIF）统一转成 JPEG
 * - 浏览器若不支持 HEIC 解码，会保留原 blob 由后端处理
 *
 * @param {File} file 原始文件
 * @param {Object} opts
 * @param {number} opts.maxSize  单边最大像素，默认 1920
 * @param {number} opts.quality  JPEG 质量 0-1，默认 0.85
 * @param {number} opts.maxBytes 触发压缩的阈值，默认 2MB
 * @returns {Promise<File>} 处理后的 File 对象（始终是 image/jpeg）
 */
export async function preprocessImage(file, opts = {}) {
  const { maxSize = 1920, quality = 0.85, maxBytes = 2 * 1024 * 1024 } = opts

  // 小于阈值且是浏览器通用格式，直接返回（转成 File 保持类型一致）
  if (file.size <= maxBytes && /\.(jpe?g|png|webp|gif)$/i.test(file.name)) {
    return file
  }

  try {
    const bitmap = await loadBitmap(file)
    const canvas = document.createElement('canvas')
    let { width, height } = bitmap

    // 等比缩放
    if (width > maxSize || height > maxSize) {
      if (width >= height) {
        height = Math.round((height * maxSize) / width)
        width = maxSize
      } else {
        width = Math.round((width * maxSize) / height)
        height = maxSize
      }
    }

    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(bitmap, 0, 0, width, height)

    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', quality)
    )

    if (!blob) return file // 转换失败则回退原文件

    // 生成新文件名（统一 .jpg）
    const baseName = file.name.replace(/\.[^.]+$/, '')
    return new File([blob], `${baseName}.jpg`, { type: 'image/jpeg' })
  } catch (e) {
    // 解码失败（如浏览器不支持 HEIC），返回原文件交给后端处理
    console.warn('图片预处理失败，使用原文件:', e)
    return file
  }
}

async function loadBitmap(file) {
  // 优先用 createImageBitmap（性能更好，支持更多格式）
  if ('createImageBitmap' in window) {
    try {
      return await createImageBitmap(file)
    } catch (e) {
      // 落到 Image 方案
    }
  }
  // 兜底：用 HTMLImageElement + URL.createObjectURL
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(img.src)
      resolve(img)
    }
    img.onerror = (e) => {
      URL.revokeObjectURL(img.src)
      reject(e)
    }
    img.src = URL.createObjectURL(file)
  })
}
