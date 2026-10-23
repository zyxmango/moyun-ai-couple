# 情侣 App 打包成 Android 安装包(APK)完整流程

> 本文档记录将本项目(Vue 3 前端 + FastAPI 后端)打包成 Android 手机安装包的完整过程,适用于零基础学习。每一步都包含"为什么做"和"怎么做"两部分。

---

## 一、整体架构与原理

### 1.1 为什么 Web 项目能变成手机 App?

本项目原本是 **Web 应用**:
- 前端:Vue 3 SPA(单页应用),跑在浏览器里
- 后端:FastAPI,跑在服务器(或本机)

要变成手机 App,关键是 **Capacitor**——一个由 Ionic 团队开发的"桥接层":

```
┌─────────────────────────────────────────┐
│         Android APK(手机安装包)          │
│  ┌───────────────────────────────────┐  │
│  │  WebView(原生 Android 组件)       │  │
│  │  ┌─────────────────────────────┐ │  │
│  │  │  你的 Vue 前端 dist 静态文件 │ │  │
│  │  │  (HTML/CSS/JS,打包进 APK)   │ │  │
│  │  └─────────────────────────────┘ │  │
│  └───────────────────────────────────┘  │
│         ↓ HTTP/WebSocket                │
│  ┌───────────────────────────────────┐  │
│  │  Capacitor Native Bridge(原生桥)│  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
              ↓ 公网请求
┌─────────────────────────────────────────┐
│  你的后端 FastAPI(通过 ngrok 暴露)     │
└─────────────────────────────────────────┘
```

**原理**:Capacitor 把你的 `dist/` 静态文件塞进一个原生 Android WebView 里,WebView 充当"应用内浏览器"加载这些页面。同时 Capacitor 提供 JS 与原生系统(相机、文件、推送等)通信的桥。最终产出一个 `.apk` 文件,可以像普通 App 一样安装。

### 1.2 为什么需要 ngrok?

手机装上 App 后,要访问后端 API。但后端跑在你本机 `localhost:8000`,手机访问不到。**ngrok** 做内网穿透:它给你一个公网域名(如 `https://xxx.ngrok-free.app`),所有请求转发到你本机的 8000 端口。

> **缺点**:ngrok 免费版地址会变、电脑关机就断。长期方案见文末第七节。

---

## 二、前置准备

### 2.1 环境清单

| 工具 | 版本要求 | 用途 |
|------|---------|------|
| Node.js | 18+ | 前端构建 |
| npm | 随 Node 安装 | 包管理 |
| Python + conda | 3.10+ | 后端运行环境 |
| Android Studio | 最新版 | Android 工程构建/打包 APK |
| JDK | 21(Android Studio 自带) | Gradle 编译 |
| ngrok | v3 | 内网穿透(临时公网访问) |

### 2.2 项目代码改造要点

在打包前,前端代码必须做这几处改造,否则 App 内访问后端会出错:

#### (1) API 地址改用环境变量
`src/api/index.js` 中 `baseURL` 不能写死,要从 `import.meta.env.VITE_API_BASE` 读:
```js
const API_BASE = import.meta.env.VITE_API_BASE || ''
const api = axios.create({ baseURL: API_BASE + '/api' })
```
**为什么**:本地开发用 `''`(走 Vite 代理),打包成 App 时要指向 ngrok 公网地址。

#### (2) Router 改 hash 模式
`src/router/index.js`:
```js
import { createRouter, createWebHashHistory } from 'vue-router'
const router = createRouter({
  history: createWebHashHistory(),  // 不是 createWebHistory
  routes: [...]
})
```
**为什么**:WebView 加载本地 `file://` 协议,HTML5 history 模式会导致路由刷新 404;hash 模式用 `#/` 锚点,兼容性好。

#### (3) WebSocket 地址从 API 推导
```js
const wsBaseUrl = API_BASE.replace(/^http/, 'ws')
const wsUrl = `${wsBaseUrl}/ws/chat?token=${token}`
```
**为什么**:`https://` 公网地址对应的 WebSocket 是 `wss://`,不能写死 `ws://localhost`。

#### (4) 图片路径拼接完整 URL
后端返回的图片路径是相对的(如 `/uploads/photos/xxx.jpg`),前端 `<img>` 要拼完整:
```js
const fullUrl = (path) => path ? (API_BASE + path) : ''
```
**为什么**:WebView 里相对路径会指向 `file://` 本地,必须拼出完整公网 URL。

---

## 三、Capacitor 集成(一次性配置)

> 这部分只做一次,后续打包不用重复。

### 3.1 安装 Capacitor

在 `frontend` 目录:
```bash
npm install @capacitor/core @capacitor/cli
npm install @capacitor/android
```

### 3.2 初始化配置

创建 `capacitor.config.ts`(在 `frontend` 根目录):
```ts
import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.couple.app',       // Android 包名,唯一标识
  appName: '情侣空间',
  webDir: 'dist',                // Vue build 产物目录
  server: {
    androidScheme: 'https'      // WebView 用 https 协议加载
  }
}
export default config
```

**关键字段说明**:
- `appId`:Android 包名,反向域名格式,发布到应用商店后不可改
- `webDir`:指向 `vite build` 的输出目录,必须是 `dist`
- `androidScheme: 'https'`:让 WebView 用 `https://` 协议而非 `file://`,避免混合内容限制

### 3.3 添加 Android 平台

```bash
npx cap add android
```

这会生成 `frontend/android/` 目录——一个完整的 Android 工程(Gradle 项目)。之后 Android Studio 打开的就是这个目录。

---

## 四、构建与打包(每次更新代码后重复)

### 4.1 第一步:配置 API 地址

编辑 `frontend/.env.production`:
```
VITE_API_BASE=https://你的-ngrok-地址.ngrok-free.dev
```

> **重要**:ngrok 地址每次重启可能变,变了就要改这里,然后重新走 4.2~4.4。

### 4.2 第二步:启动后端 + ngrok 拿公网地址

两个终端分别运行:

**终端 1 - 后端**(在 `backend` 目录):
```bash
# Windows 用 conda 环境运行
conda run -n couple-app-ai --no-capture-output python run.py
```
看到 `Uvicorn running on http://127.0.0.1:8000` 即成功。

**终端 2 - ngrok**(在 `ngrok` 目录):
```bash
.\ngrok.exe http 8000
```
看到一行:
```
Forwarding  https://xxxx-xxxx.ngrok-free.dev -> http://localhost:8000
```
**记下这个 https 地址**,填到 4.1 的 `.env.production` 里。

### 4.3 第三步:构建前端 + 同步到 Android 工程

在 `frontend` 目录:
```bash
npm run build         # 生成 dist/
npx cap copy          # 把 dist/ 复制进 android/app/src/main/assets/public/
```

**两步的作用**:
- `npm run build`:Vue 源码 → 优化压缩后的静态文件(JS/CSS/HTML),输出到 `dist/`
- `npx cap copy`:把 `dist/` 内容复制到 Android 工程里,WebView 运行时加载的就是这些文件

### 4.4 第四步:Android Studio 打包 APK

#### (1) 用 Android Studio 打开工程
在 `frontend` 目录运行:
```bash
npx cap open android
```
或手动打开 Android Studio → Open → 选 `d:\couple-app-ai\frontend\android` 目录。

#### (2) Gradle Sync(首次必做)
打开后右下角会自动开始 **Gradle Sync**。首次会下载 Gradle 和 Android SDK 组件,耗时较长。

**国内加速配置**(避免 timeout,首次必改):

**`android/gradle/wrapper/gradle-wrapper.properties`**——把 distributionUrl 改成腾讯云镜像:
```
distributionUrl=https://mirrors.cloud.tencent.com/gradle/gradle-8.x.x-bin.zip
```

**`android/settings.gradle`**——pluginManagement 和 dependencyResolutionManagement 的 repositories 改阿里云:
```
pluginManagement {
    repositories {
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/public' }
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        maven { url 'https://maven.aliyun.com/repository/google' }
        maven { url 'https://maven.aliyun.com/repository/public' }
        google()
        mavenCentral()
    }
}
```

**`android/build.gradle`**——buildscript 和 allprojects 加阿里云镜像(同上 repositories 块)。

改完点顶部 **大象图标 Sync Now**,绿色勾 ✅ 表示成功。

#### (3) 构建 APK
顶部菜单:**Build → Generate App Bundles or APKs → Build APK(s)**

构建完成后右下角弹通知,点 **locate** 找到 APK,路径固定为:
```
d:\couple-app-ai\frontend\android\app\build\outputs\apk\debug\app-debug.apk
```

这是 **debug 版 APK**(未签名),体积小(约 4-5MB),仅用于自己测试安装。

---

## 五、安装到手机

1. **传输 APK**:用微信/QQ/USB 把 `app-debug.apk` 发到手机
2. **允许未知来源**:手机点开 APK 会提示"未知来源",按提示到 **设置 → 安全 → 允许安装未知应用** 给文件管理器/浏览器授权
3. **安装**:点开 APK → 安装 → 完成
4. **验证**:打开 App,登录,测试相册、聊天等功能

> **更新 App**:重新打包后,要先在手机上**卸载旧版**再装新版,否则签名冲突装不上(debug 签名每次可能不同)。

---

## 六、常见问题排查

### 6.1 登录提示 "Network Error"

**根因**:ngrok 免费版首次访问会返回一个 HTML 警告页("You are about to visit..."),不是直接转发到后端。axios 收到 HTML 解析 JSON 失败就报 Network Error。

**修复**:在 `src/api/index.js` 的请求拦截器加 header 跳过警告页:
```js
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (API_BASE) {
    config.headers['ngrok-skip-browser-warning'] = 'true'  // 关键
  }
  return config
})
```

### 6.2 相册图片不显示 / 内容空白

**排查顺序**(不要跳步):
1. **后端是否在跑**?本机访问 `http://127.0.0.1:8000/health`,应返回 `{"status":"ok"}`
2. **ngrok 是否在跑**?访问 `https://你的-ngrok地址.ngrok-free.dev/health`(带 skip header),应返回 ok。若返回 `ERR_NGROK_3200` 说明 ngrok 断了,重启 ngrok
3. **502 Bad Gateway**?ngrok 活着但后端没起来,重启后端
4. **图片 URL 直测**:浏览器访问 `https://ngrok地址/uploads/avatars/xxx.jpg`,应返回 200 + image/jpeg
5. **检查前端拼接**:`<img :src="API_BASE + photo.url">` 必须拼成完整公网 URL

### 6.3 Gradle Sync timeout / 下载失败

**根因**:默认从 Google/Maven 中央仓库下载,国内访问慢/超时。

**修复**:按 4.4(2)配置腾讯云 Gradle 镜像 + 阿里云 Maven 镜像。

### 6.4 后端启动后立即 502

**根因**:后端 WatchFiles 模式有时会卡在 reloader 进程,server process 没启动。

**修复**:用无重载模式启动:
```bash
conda run -n couple-app-ai python -c "import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8000, reload=False)"
```

---

## 七、长期稳定方案(强烈建议)

ngrok 免费版 + 电脑当服务器有以下致命问题:
- ❌ 电脑关机/休眠 → App 整体不可用
- ❌ ngrok 重启 → 地址变化 → APK 里写死的地址失效 → 需重新打包
- ❌ 免费版有连接数和带宽限制
- ❌ 家庭宽带可能封 80/443 端口

### 推荐方案(按优先级)

| 方案 | 适合场景 | 成本 | 地址是否固定 |
|------|---------|------|-------------|
| **云服务器 + 域名 + HTTPS** | 长期正式使用 | 约 ¥50-100/月(轻量云机) | ✅ 固定 |
| **Cloudflare Tunnel** | 有公网 IP 但要固定域名 | 免费 | ✅ 固定(用自己域名) |
| **ngrok 付费版** | 临时但需稳定 | $8/月起 | ✅ 固定(保留子域名) |

**最推荐**:买一台轻量云服务器(阿里云/腾讯云学生机),部署后端,绑域名+Let's Encrypt 免费 SSL 证书。然后 `.env.production` 里写固定域名,一次打包永久可用。

---

## 八、流程速查表(每次更新代码后)

```
1. 改代码 → git 提交(可选)
2. 启动后端:conda run -n couple-app-ai python run.py
3. 启动 ngrok:.\ngrok.exe http 8000 → 记下 https 地址
4. 改 .env.production 的 VITE_API_BASE = 新地址
5. cd frontend && npm run build && npx cap copy
6. Android Studio:Build → Build APK(s)
7. 卸载手机旧版 → 装新版 APK
```

---

## 九、关键文件索引

| 文件 | 作用 |
|------|------|
| `frontend/.env.production` | 打包时的 API 地址配置 |
| `frontend/capacitor.config.ts` | Capacitor 配置(包名、webDir) |
| `frontend/src/api/index.js` | axios 实例 + 请求拦截器(ngrok header) |
| `frontend/src/router/index.js` | 路由配置(hash 模式) |
| `frontend/android/` | Android 原生工程(Gradle 项目) |
| `frontend/android/app/src/main/AndroidManifest.xml` | Android 权限声明(INTERNET) |
| `frontend/android/gradle/wrapper/gradle-wrapper.properties` | Gradle 版本+镜像 |
| `frontend/android/settings.gradle` | Maven 仓库镜像配置 |
| `backend/app/main.py` | FastAPI 入口 + 静态文件挂载 `/uploads` |

---

*文档版本:2026-08-31*
