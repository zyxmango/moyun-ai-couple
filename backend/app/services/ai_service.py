"""AI 服务封装：兼容 OpenAI 接口，无 API Key 时回退规则模板"""
import json
import logging
import re
from typing import List, Dict, Optional

from ..config import settings


logger = logging.getLogger(__name__)


class AIService:
    def __init__(self):
        self.api_key = settings.AI_API_KEY
        self.api_base = settings.AI_API_BASE
        self.model = settings.AI_MODEL
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        temperature: float = 0.8,
        max_tokens: int = 1024,
    ) -> str:
        """调用 LLM 对话，无 API Key 时使用规则模板"""
        if self.available:
            try:
                full_messages = []
                if system_prompt:
                    full_messages.append({"role": "system", "content": system_prompt})
                full_messages.extend(messages)
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content.strip()
            except Exception:
                logger.exception("AI service call failed; using the local fallback")
                return self._fallback_chat(messages, system_prompt)
        return self._fallback_chat(messages, system_prompt)

    def _fallback_chat(self, messages: List[Dict[str, str]], system_prompt: str) -> str:
        """无 API Key 时的规则模板回复，保证测试可用"""
        last_user = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_user = m["content"]
                break

        if "约会规划 Agent" in system_prompt:
            city_match = re.search(r"城市：([^\n]*)", last_user)
            budget_match = re.search(r"预算：([^\n]*)", last_user)
            duration_match = re.search(r"时长：([^\n]*)", last_user)
            city = (city_match.group(1).strip() if city_match else "本地") or "本地"
            budget = (budget_match.group(1).strip() if budget_match else "灵活") or "灵活"
            duration = (duration_match.group(1).strip() if duration_match else "半天") or "半天"
            source_lines = [line for line in last_user.splitlines() if re.match(r"\[\d+\]", line.strip())]
            basis = "\n".join(source_lines[:3]) or "暂无可引用的偏好记录，本方案仅按本次输入生成。"
            return (
                f"## {city} · {duration}约会方案\n\n"
                f"**预算范围：** {budget}\n\n"
                "1. **轻松开场**：选择交通方便的咖啡馆或公园，预留 60 分钟聊天。\n"
                "2. **共同体验**：安排一项可协作的活动，如展览、手作、桌游或一起做饭。\n"
                "3. **温柔收尾**：用餐后散步，并各自分享今天最喜欢的一个瞬间。\n\n"
                "### 规划依据\n"
                f"{basis}\n\n"
                "### 备选方案\n"
                "如遇下雨或临时疲惫，可改为室内电影 + 一起挑选晚餐，保留弹性。\n\n"
                "（当前为本地可执行方案；配置 AI_API_KEY 后会结合更多细节生成个性化路线。）"
            )

        if "共同记忆周报" in system_prompt:
            records = [
                line[2:].strip()
                for line in last_user.splitlines()
                if line.strip().startswith("- ")
            ]
            if not records:
                return (
                    "【共同记忆周报】\n本周期还没有可用的共同记忆。"
                    "可以先同步日记、聊天、相册或纪念日，再来生成回顾。"
                )
            highlights = "\n".join(f"- {item}" for item in records[:5])
            return (
                "【共同记忆周报】\n"
                f"本周期记录了 {len(records)} 个共同片段：\n{highlights}\n\n"
                "互动建议：一起挑选其中一个片段，说说当时最难忘的细节。\n"
                "（当前为基于真实记录的本地摘要；配置 AI_API_KEY 后可获得更自然的回顾。）"
            )

        if "共同记忆助手" in system_prompt:
            context_match = re.search(r"【共同记忆】\s*(.*?)\s*【问题】", last_user, re.S)
            context = context_match.group(1).strip() if context_match else ""
            evidence = [line.strip() for line in context.splitlines() if line.strip()]
            if not evidence or "没有找到" in context:
                return "我还没在你们的共同记忆里找到这件事。等你们记录下更多细节后，再来问我吧。"
            first = evidence[0].split("；内容：", 1)[-1].strip()
            return f"我记得你们提到过：{first[:180]}。如果你愿意，也可以再告诉我更多细节，我会帮你们把这段回忆记得更完整。"

        if "陪伴" in system_prompt or "情感" in system_prompt:
            return (
                f"我听到你说「{last_user}」，谢谢你愿意和我分享。\n"
                "在恋爱中，坦诚表达自己的感受是非常珍贵的。"
                "建议你试着和伴侣平静地聊聊内心想法，相互倾听比解决问题本身更重要。\n"
                "（注：当前未配置 AI API Key，此为离线模板回复。配置 .env 中的 AI_API_KEY 后可获得真实的 AI 对话体验。）"
            )
        if "总结" in system_prompt or "日记" in system_prompt:
            return (
                "【情感总结报告（离线模板）】\n"
                f"近期记录关键词：{last_user[:80]}\n"
                "情绪倾向：整体积极，偶有小波动，属于健康的恋爱状态。\n"
                "建议：继续保持沟通，多创造共同回忆。\n"
                "（注：配置 AI_API_KEY 后可获得个性化智能总结。）"
            )
        if "文案" in system_prompt or "生成" in system_prompt:
            return (
                f"【专属文案（离线模板）】\n"
                f"关键词：{last_user}\n\n"
                "愿我们的每一天都如初见般心动，时光不老，我们不散。\n"
                "（注：配置 AI_API_KEY 后可获得个性化 AI 文案生成。）"
            )
        if "旅游" in system_prompt or "RAG" in system_prompt:
            return (
                "根据你的旅游记录，我整理了以下信息（离线模板）：\n"
                f"关于「{last_user}」，建议你回顾上传的旅行文档获取详细内容。\n"
                "（注：配置 AI_API_KEY 后可获得基于知识库的智能问答。）"
            )
        return (
            f"收到你的消息：「{last_user}」。\n"
            "（注：当前未配置 AI API Key，此为离线模板回复。）"
        )

    def companion_chat(self, user_message: str, history: List[Dict], memory_context: str = "") -> str:
        system = (
            "你是常驻在情侣应用里的专属情侣助手“小忆”。"
            "你既能倾听和提供温和、可执行的相处建议，也能根据共同记忆回答两个人的经历、偏好和计划。"
            "回答自然、亲切、简洁，像熟悉他们故事的朋友，通常控制在2到5句话，不过度煽情或说教。"
            "只把下方资料当作内部参考，不要展示检索过程、来源、编号或原始片段。"
            "用户询问时间且资料中有明确日期时，必须直接给出日期；没有明确日期时才说明暂时无法确认。"
            "不能从旧记录推断伴侣此刻的位置、行为或情绪；资料没有写明时要坦诚说还不知道。"
            "不要进行心理诊断，不替用户做关系决定，也不要编造任何两人的事实。"
        )
        if memory_context:
            system += f"\n\n可参考的共同记忆：\n{memory_context}"
        messages = history + [{"role": "user", "content": user_message}]
        return self.chat(messages, system_prompt=system)

    def generate_content(self, scene: str, keywords: str, extra: str = "") -> str:
        scene_map = {
            "anniversary": "纪念日祝福文案",
            "date": "约会方案",
            "keyword": "个性化文案",
        }
        scene_desc = scene_map.get(scene, "个性化文案")
        system = "你是一位擅长创作浪漫文案的 AI，根据用户需求生成温馨、有创意的情侣专属内容。"
        prompt = f"请生成一份{scene_desc}。关键词：{keywords}。{('额外要求：' + extra) if extra else ''}"
        return self.chat([{"role": "user", "content": prompt}], system_prompt=system)

    def diary_summary(self, diary_texts: List[str], period: str) -> str:
        system = (
            "你是一位情感分析 AI，请根据情侣日记内容生成情感总结报告。"
            "报告需包含：关键事件回顾、情绪倾向分析、关系健康度评估、温馨建议。"
            "语气温暖，结构清晰。"
        )
        joined = "\n---\n".join(diary_texts) if diary_texts else "（近期暂无日记记录）"
        prompt = f"请根据以下{period}的情侣日记内容，生成情感总结报告：\n\n{joined}"
        return self.chat([{"role": "user", "content": prompt}], system_prompt=system, max_tokens=1500)

    def rag_answer(self, question: str, context: str, history: List[Dict]) -> str:
        system = (
            "你是一个旅游记录智能助手。请根据提供的旅游知识库内容回答用户问题。"
            "回答需基于知识库信息，不可编造。如知识库中无相关信息，请如实告知。"
            "回复语气亲切，适合情侣阅读。"
        )
        prompt = f"【知识库参考内容】\n{context}\n\n【用户问题】\n{question}"
        messages = history + [{"role": "user", "content": prompt}]
        return self.chat(messages, system_prompt=system, max_tokens=1200)

    def extract_memory(self, text: str, source_title: str = "") -> Dict:
        """将原始内容提取为结构化记忆；模型不可用时使用可测试的规则降级。"""
        fallback = self._fallback_memory_extract(text, source_title)
        if not self.available:
            return fallback

        system = (
            "你是共同记忆信息抽取器。只输出 JSON，不要输出解释。字段必须包含："
            "title、summary、event_date、location、emotion、tags、importance。"
            "event_date 无法确定时为空字符串；importance 为 0 到 1。"
        )
        prompt = f"来源标题：{source_title}\n原始内容：\n{text[:4000]}"
        raw = self.chat(
            [{"role": "user", "content": prompt}],
            system_prompt=system,
            temperature=0.1,
            max_tokens=600,
        )
        try:
            match = re.search(r"\{[\s\S]*\}", raw)
            data = json.loads(match.group(0) if match else raw)
            return {
                "title": str(data.get("title") or fallback["title"])[:200],
                "summary": str(data.get("summary") or fallback["summary"])[:2000],
                "event_date": str(data.get("event_date") or "")[:32],
                "location": str(data.get("location") or "")[:100],
                "emotion": str(data.get("emotion") or "")[:30],
                "tags": [str(x)[:30] for x in (data.get("tags") or [])][:8],
                "importance": max(0.0, min(1.0, float(data.get("importance", 0.5)))),
            }
        except Exception:
            return fallback

    def _fallback_memory_extract(self, text: str, source_title: str = "") -> Dict:
        clean = re.sub(r"\s+", " ", text).strip()
        emotion = ""
        emotion_map = {
            "开心": ("开心", "快乐", "幸福", "惊喜", "甜蜜"),
            "想念": ("想念", "思念", "等你"),
            "难过": ("难过", "伤心", "失落", "委屈"),
            "期待": ("期待", "计划", "想去", "约定"),
        }
        for label, words in emotion_map.items():
            if any(word in clean for word in words):
                emotion = label
                break
        locations = re.findall(r"([\u4e00-\u9fa5]{2,8}(?:市|区|县|景区|公园|餐厅|酒店))", clean)
        tags = []
        for word in ("旅行", "约会", "生日", "纪念日", "电影", "美食", "礼物", "计划"):
            if word in clean:
                tags.append(word)
        return {
            "title": (source_title or clean[:24] or "共同记忆")[:200],
            "summary": clean[:800],
            "event_date": "",
            "location": locations[0] if locations else "",
            "emotion": emotion,
            "tags": tags,
            "importance": 0.7 if any(x in clean for x in ("第一次", "生日", "纪念", "旅行")) else 0.5,
        }

    def memory_answer(self, question: str, context: str, history: List[Dict] | None = None) -> str:
        system = (
            "你是专属于一对情侣的共同记忆助手。只能依据给出的共同记忆回答，绝对不可编造。"
            "请像熟悉他们故事的温暖朋友一样直接回答：自然、亲切、简洁，不过度煽情，也不要使用客服腔。"
            "不要展示检索过程，不要提到来源、片段、编号或共同记忆库，不要使用[1][2]等引用标记。"
            "记录时间不等于事件发生时间；用户询问具体日期而记录中没有明确日期时，要温和地说明目前只能确认事件，无法确认具体时间。"
            "多条记录互相矛盾时应指出暂时无法确定，并邀请两个人补充或确认。"
            "信息不足时，用第一人称简短说明自己还没记住这件事，并邀请用户补充。"
            "不要进行心理诊断，也不要替用户做关系决定。回答通常控制在2到4句话。"
        )
        prompt = f"【共同记忆】\n{context}\n\n【问题】\n{question}"
        return self.chat((history or []) + [{"role": "user", "content": prompt}], system_prompt=system, max_tokens=1000)

    def memory_report(self, memories: List[Dict], period_label: str) -> str:
        context = "\n".join(
            f"- {m.get('event_date') or ''} {m.get('title') or ''}: {m.get('content') or ''}"
            for m in memories
        )
        system = (
            "你是情侣共同记忆周报助手。根据真实记录生成温暖的回顾，包含共同事件、"
            "情绪亮点、即将到来的事项和一个轻量互动建议。不得进行感情打分或心理诊断。"
        )
        prompt = f"请生成{period_label}共同记忆报告。真实记录如下：\n{context or '本周期暂无记录'}"
        return self.chat([{"role": "user", "content": prompt}], system_prompt=system, max_tokens=1200)

    def date_plan(self, request: Dict, memories: List[Dict]) -> str:
        """生成受控的约会方案，明确引用参与规划的可见记忆。"""
        context = "\n".join(
            f"[{index}] {item.get('title') or ''}：{item.get('content') or ''}"
            for index, item in enumerate(memories, start=1)
        ) or "暂无共同记忆"
        system = (
            "你是面向真实情侣的约会规划 Agent。只能使用用户本次输入和给出的可见记忆，"
            "不得泄露不可见记忆，不得捏造具体商家、价格或开放时间。输出可执行的时间安排、"
            "预算分配、规划依据和一个天气/体力变化时的备选方案；引用记忆时使用[1][2]。"
        )
        prompt = (
            f"城市：{request.get('city') or '未指定'}\n"
            f"日期：{request.get('desired_date') or '未指定'}\n"
            f"预算：{request.get('budget') or '未指定'}\n"
            f"时长：{request.get('duration') or '半天'}\n"
            f"本次偏好：{request.get('preferences') or '无'}\n"
            f"需要避开：{request.get('avoid') or '无'}\n\n"
            f"【可见记忆】\n{context}"
        )
        return self.chat([{"role": "user", "content": prompt}], system_prompt=system, temperature=0.5, max_tokens=1400)


ai_service = AIService()
