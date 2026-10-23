<template>
  <main class="explore-page" :class="{ 'life-page': isLife }">
    <section class="intro">
      <span class="eyebrow">{{ isLife ? 'OUR EVERYDAY' : 'AI FOR TWO' }}</span>
      <h1>{{ isLife ? '平凡日常，也值得珍藏。' : '因为记得，所以更懂你们。' }}</h1>
      <p>{{ isLife ? '把日子过成故事，把喜欢留在这里。' : '从共同经历出发，找回回忆，也为下一次心动做准备。' }}</p>
    </section>

    <template v-if="!isLife">
      <router-link to="/ai/memory" class="memory-card">
        <div class="memory-top"><span>✦ 共享记忆</span><span>小忆的记忆库</span></div>
        <h2>你们的故事，<br>每一段都有回声。</h2>
        <p>聊天、日记、照片与纪念日，让重要的细节被记住。</p>
        <div class="memory-bottom"><span>试着问：“我们第一次旅行去了哪里？”</span><b>打开记忆 →</b></div>
      </router-link>
      <div class="group-label"><h2>为下一次心动准备</h2><span>灵感与陪伴</span></div>
      <div class="ai-tools">
        <router-link v-for="item in aiTools" :key="item.path" :to="item.path" class="tool-card">
          <el-icon class="tool-icon"><component :is="item.icon" /></el-icon>
          <h3>{{ item.title }}</h3><p>{{ item.desc }}</p><span class="card-arrow">↗</span>
        </router-link>
      </div>
    </template>

    <template v-else>
      <div class="life-cards">
        <router-link v-for="item in lifeTools" :key="item.path" :to="item.path" class="archive-card" :class="item.tone">
          <div class="archive-top"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></div>
          <h2>{{ item.title }}</h2><p>{{ item.desc }}</p>
          <span class="archive-open">{{ item.action }} <b>→</b></span>
        </router-link>
      </div>
      <p class="closing-note">不必每一天都特别，记录下来就有意义。</p>
    </template>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Bell, Calendar, Document, Food, Location, MagicStick, Notebook, Picture, Position } from '@element-plus/icons-vue'

const route = useRoute()
const isLife = computed(() => route.path === '/life')
const aiTools = [
  { path: '/ai/date-plan', title: '约会规划', desc: '结合彼此的偏好，安排一次期待的见面。', icon: Position },
  { path: '/ai/reminders', title: '智能提醒', desc: '重要日子和共同约定，提前一点准备。', icon: Bell },
  { path: '/ai/summary', title: '关系回顾', desc: '回望这段时间，发现相处中的小美好。', icon: Document },
  { path: '/ai/generate', title: '心意表达', desc: '把心里的喜欢，变成贴近你们的话。', icon: MagicStick },
  { path: '/ai/rag', title: '共同旅行', desc: '带着共同偏好，计划下一段远方。', icon: Location },
]
const lifeTools = [
  { path: '/anniversary', title: '纪念日', label: 'IMPORTANT DAYS', desc: '第一次相遇、每一个生日，还有属于你们的日子。', action: '看看重要日子', icon: Calendar, tone: 'rose' },
  { path: '/album', title: '共同相册', label: 'LITTLE MOMENTS', desc: '镜头里的风景，和风景里最想留住的人。', action: '翻翻照片', icon: Picture, tone: 'sage' },
  { path: '/diary', title: '两人日记', label: 'DEAR US', desc: '今天的小事、没说完的话，都写给彼此。', action: '打开日记', icon: Notebook, tone: 'cream' },
  { path: '/recipe', title: '两人厨房', label: 'MADE WITH LOVE', desc: '记住彼此爱吃什么，也收藏一起下厨的味道。', action: '今天吃什么', icon: Food, tone: 'peach' },
]
</script>

<style scoped>
.explore-page{max-width:720px;margin:auto;padding:20px 20px 32px;color:#302b27;background:#f7f4ef;min-height:calc(100dvh - 64px)}
.intro{padding:12px 2px 24px}.eyebrow{font-size:9px;letter-spacing:2px;color:#ae7369}.intro h1{font:600 25px/1.5 serif;margin:10px 0}.intro p{font-size:12px;line-height:1.8;color:#8a7c71}
.memory-card{display:block;position:relative;overflow:hidden;padding:24px;border-radius:22px;background:linear-gradient(130deg,#45332f,#71534b);color:#fff6ef;text-decoration:none;box-shadow:0 12px 26px #5b3c3417}.memory-top{display:flex;justify-content:space-between;gap:10px;font-size:11px;color:#e6b9ac}.memory-top span:last-child{color:#d0b5a9;font-size:10px}.memory-card h2{position:relative;font:500 27px/1.5 serif;margin:24px 0 14px;letter-spacing:2px}.memory-card p{max-width:310px;font-size:12px;line-height:1.9;color:#dfcbc0}.memory-bottom{position:relative;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px;margin-top:24px;padding-top:16px;border-top:1px solid #ffffff20}.memory-bottom span{font-size:10px;color:#d1b8ab}.memory-bottom b{font-size:12px;font-weight:500}
.group-label{display:flex;justify-content:space-between;align-items:center;margin:26px 0 13px}.group-label h2{font:600 17px serif}.group-label span{color:#a29488;font-size:10px}.ai-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.tool-card{position:relative;display:block;padding:20px 16px;border:1px solid #e9ded5;border-radius:17px;background:#fffdf9;text-decoration:none;color:inherit}.tool-icon{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:#f2e4df;color:#b57569;font-size:19px}.tool-card h3{margin:15px 0 8px;font-size:15px}.tool-card p{color:#928176;font-size:12px;line-height:1.8}.card-arrow{position:absolute;top:17px;right:16px;color:#b5a397}.tool-card:last-child{grid-column:1/-1}
.life-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.archive-card{display:flex;flex-direction:column;min-width:0;padding:22px 18px;border:1px solid #e6d9ce;border-radius:21px;color:#443a31;text-decoration:none}.rose{background:linear-gradient(145deg,#f1dcd8,#fff7f2)}.sage{background:linear-gradient(145deg,#dfe7dc,#f6f8f0)}.cream{background:linear-gradient(145deg,#ede1c8,#fff9ed)}.peach{background:linear-gradient(145deg,#f2dfcf,#fff7ef)}.archive-top{display:flex;flex-direction:column;gap:20px;color:#99796a}.archive-top .el-icon{font-size:30px}.archive-top span{font-size:8px;letter-spacing:1.5px}.archive-card h2{margin:12px 0 10px;font:600 22px serif}.archive-card p{font-size:12px;line-height:1.9;color:#8c7c6e}.archive-open{margin-top:auto;padding-top:28px;font-size:11px;color:#776053}.archive-open b{margin-left:8px}.closing-note{margin:26px 0 8px;text-align:center;color:#a39588;font:12px/1.8 serif}
@media(max-width:360px){.explore-page{padding:16px 12px 28px}.intro h1{font-size:22px}.archive-card{padding:18px 13px}.life-cards{gap:10px}}
</style>
