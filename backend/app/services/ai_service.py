"""AI 服务封装：兼容 OpenAI 接口，无 API Key 时回退规则模板"""
import json
import hashlib
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import List, Dict, Optional

import numpy as np

from ..config import settings


logger = logging.getLogger(__name__)
_usage_context = ContextVar("ai_usage_context", default=None)


class AIService:
    @contextmanager
    def track_usage(self):
        """按当前线程/异步上下文统计模型调用与 Token，不记录聊天正文。"""
        stats = {
            "model_calls": 0, "embedding_calls": 0,
            "input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0,
        }
        token = _usage_context.set(stats)
        try:
            yield stats
        finally:
            _usage_context.reset(token)

    @staticmethod
    def _record_usage(response, embedding: bool = False):
        stats = _usage_context.get()
        if stats is None:
            return
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        if embedding:
            stats["embedding_calls"] += 1
            stats["embedding_tokens"] += total_tokens or prompt_tokens
        else:
            stats["model_calls"] += 1
            stats["input_tokens"] += prompt_tokens
            stats["output_tokens"] += completion_tokens

    @staticmethod
    def _unit_float(value, default: float = 0.5) -> float:
        """Normalize model confidence fields without letting loose labels stop syncing."""
        labels = {
            "low": 0.3,
            "medium": 0.5,
            "high": 0.8,
            "低": 0.3,
            "中": 0.5,
            "高": 0.8,
        }
        try:
            number = float(labels.get(str(value).strip().lower(), value))
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(1.0, number))

    def __init__(self):
        self.api_key = settings.AI_API_KEY
        self.api_base = settings.AI_API_BASE
        self.model = settings.AI_MODEL
        self.embedding_model = settings.AI_EMBEDDING_MODEL
        self.enable_thinking = settings.AI_ENABLE_THINKING
        self.memory_summary_with_model = settings.AI_MEMORY_SUMMARY_WITH_MODEL
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
                    **self._thinking_options(),
                )
                self._record_usage(resp)
                return resp.choices[0].message.content.strip()
            except Exception:
                logger.exception("AI service call failed; using the local fallback")
                return self._fallback_chat(messages, system_prompt)
        return self._fallback_chat(messages, system_prompt)

    def _thinking_options(self) -> Dict:
        """Qwen 3.8 默认使用最高思考强度；结构化记忆任务显式按配置关闭。"""
        if "dashscope" in self.api_base and self.model.startswith("qwen3.8"):
            return {"extra_body": {"enable_thinking": self.enable_thinking}}
        return {}

    def _chat_strict(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """用于不可丢失的后台整理：调用失败时抛错，让同步游标留在原处重试。"""
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **self._thinking_options(),
        )
        self._record_usage(resp)
        return resp.choices[0].message.content.strip()

    @property
    def embedding_index_model(self) -> str:
        return self.embedding_model if self.available else "local-hash-v1"

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """返回归一化向量。在线使用语义 embedding；离线使用稳定的字符哈希向量。"""
        if not texts:
            return []
        if self.available:
            vectors = []
            batch_size = 10 if "dashscope" in self.api_base else 128
            for start in range(0, len(texts), batch_size):
                response = self._client.embeddings.create(
                    model=self.embedding_model,
                    input=texts[start:start + batch_size],
                )
                self._record_usage(response, embedding=True)
                vectors.extend(np.asarray(item.embedding, dtype=np.float32) for item in response.data)
        else:
            vectors = [self._local_hash_embedding(text) for text in texts]
        normalized = []
        for vector in vectors:
            norm = float(np.linalg.norm(vector))
            normalized.append(vector / norm if norm else vector)
        return normalized

    @staticmethod
    def _local_hash_embedding(text: str, dimensions: int = 384) -> np.ndarray:
        """无外部模型时的确定性降级索引；用于离线运行和可重复测试。"""
        clean = re.sub(r"\s+", " ", text.lower()).strip()
        vector = np.zeros(dimensions, dtype=np.float32)
        wrapped = f" {clean} "
        for size in (1, 2, 3):
            for index in range(max(0, len(wrapped) - size + 1)):
                token = wrapped[index:index + size].encode("utf-8")
                digest = hashlib.blake2b(token, digest_size=8).digest()
                value = int.from_bytes(digest, "little")
                vector[value % dimensions] += 1.0 if value & 1 else -1.0
        return vector

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
                "importance": self._unit_float(data.get("importance"), 0.5),
            }
        except Exception:
            return fallback

    def extract_memory_events(self, messages: List[Dict]) -> List[Dict]:
        """从一段连续对话中抽取事件级记忆；无记忆价值时返回空列表。"""
        if not messages:
            return []
        fallback = self._fallback_memory_events(messages)
        if not self.available:
            return self._attach_uncovered_context_facts(fallback, messages)

        compact = [
            {
                "id": item["id"],
                "sender_id": item.get("sender_id"),
                "created_at": str(item.get("created_at") or ""),
                "content": str(item.get("content") or "")[:1000],
            }
            for item in messages
        ]
        system = (
            "你是长期记忆整理器。阅读一段情侣连续聊天，把相关碎片合并为事件、偏好、事实或计划。"
            "‘嗯’‘哈哈’‘到了吗’等短句不能单独成为记忆，但可作为上下文。"
            "不得把计划写成已发生事实，不得推断聊天中没有明确表达的和好、感情状态或动机。"
            "没有值得长期保存的信息时返回空数组；每批最多提取 6 条，summary 控制在 200 字以内。"
            "只输出 JSON 数组。每项字段："
            "title、summary、category(event/preference/fact/plan)、state(planned/ongoing/completed/cancelled/uncertain)、"
            "event_kind(trip/date/conflict/gift/preference/plan/fact/activity)、event_key、entities、"
            "event_date、event_end、started_at、resolved_at、location、emotion、tags、importance、confidence、source_message_ids、facts。"
            "started_at 是事件开始时间，resolved_at 是事件完成、取消或和好的时间；未结束时 resolved_at 留空。"
            "facts 是原子事实数组，每项只包含 type、value、subject_user_id、asserted_by_user_id、occurred_at、source_message_ids；"
            "subject_user_id 是事实所描述的人，asserted_by_user_id 是说出该事实的人；只能使用输入中的 sender_id，"
            "双方共同事实或无法确定主体时 subject_user_id 填 null，不能把陈述者自动当成主体。"
            "例如抵达、游览、餐食、偏好旧值、偏好新值、取消原因、冲突原因、解决办法分别保存，不能只写概括。"
            "每个事件最多8个facts，每个value不超过100字，输出必须是紧凑且可解析的合法JSON。"
            "event_key 表示可跨批次复用的稳定身份，只能由事件类型和核心主题组成，例如"
            "trip:武汉:2019-01-06、plan:哈尔滨旅行、preference:咖啡甜度、conflict:忘记倒垃圾:2024-01-30；"
            "不能用‘我到家再说’等闲聊作event_key，同一事件的不同状态不得改变 event_key。"
            "‘我到家以后再给你发消息’‘晚饭先不用等我’等即时通知不是事件事实、计划或冲突约定，"
            "不能写入facts，也不能作为任何长期事件的证据。"
            "事实槽位必须规范：旅行使用destination/activity/meal/completion；偏好使用preference_topic/"
            "previous_preference/current_preference；计划使用plan_intent/plan_status/cancellation_reason；"
            "冲突与和好使用conflict_reason/resolution/agreement。证据明确出现的槽位不得遗漏。"
            "source_message_ids 必须只包含真正支持该结论的输入消息 id；importance 和 confidence 为 0 到 1。"
        )
        raw = self._chat_strict(
            [{"role": "user", "content": json.dumps(compact, ensure_ascii=False)}],
            system_prompt=system,
            temperature=0.1,
            max_tokens=3000,
        )
        try:
            def parse_events(value: str):
                match = re.search(r"\[[\s\S]*\]", value)
                return json.loads(match.group(0) if match else value)

            try:
                data = parse_events(raw)
            except json.JSONDecodeError:
                retry_system = system + "上一次输出格式不合法。重新生成，不要解释，不要Markdown，不要尾随逗号。"
                raw = self._chat_strict(
                    [{"role": "user", "content": json.dumps(compact, ensure_ascii=False)}],
                    system_prompt=retry_system,
                    temperature=0.0,
                    max_tokens=3200,
                )
                data = parse_events(raw)
            if isinstance(data, list) and not data and fallback:
                retry_system = system + (
                    "上一次返回了空数组，但规则检查发现输入含有长期记忆信号。"
                    "请逐条检查原始消息，只抽取有直接证据的事件；仍然没有时才返回空数组。"
                )
                raw = self._chat_strict(
                    [{"role": "user", "content": json.dumps(compact, ensure_ascii=False)}],
                    system_prompt=retry_system,
                    temperature=0.0,
                    max_tokens=3200,
                )
                data = parse_events(raw)
            if not isinstance(data, list):
                raise ValueError("memory extraction response is not a JSON array")
            allowed_ids = {int(item["id"]) for item in messages}
            events = []
            for item in data[:6]:
                if not isinstance(item, dict):
                    continue
                source_ids = []
                for value in item.get("source_message_ids") or []:
                    try:
                        message_id = int(value)
                    except (TypeError, ValueError):
                        continue
                    if message_id in allowed_ids and message_id not in source_ids:
                        source_ids.append(message_id)
                summary = str(item.get("summary") or "").strip()
                if not summary or not source_ids:
                    continue
                category = str(item.get("category") or "event").lower()
                if category not in {"event", "preference", "fact", "plan"}:
                    category = "event"
                state = str(item.get("state") or "uncertain").lower()
                if state not in {"planned", "ongoing", "completed", "cancelled", "uncertain"}:
                    state = "uncertain"
                event_kind = str(item.get("event_kind") or category).lower()
                if event_kind not in {"trip", "date", "conflict", "reconciliation", "gift", "preference", "plan", "fact", "activity"}:
                    event_kind = category
                # 计划和偏好是业务类别，也必须是事件身份类型。模型偶尔会把“旅行计划”
                # 标成 trip、把“约会计划”标成 date，造成同一计划保存两遍。
                if category in {"plan", "preference"}:
                    event_kind = category
                entities = [str(value).strip()[:80] for value in (item.get("entities") or []) if str(value).strip()][:12]
                facts = []
                for fact in (item.get("facts") or [])[:20]:
                    if not isinstance(fact, dict):
                        continue
                    value = str(fact.get("value") or "").strip()
                    if not value or self._is_routine_context(value):
                        continue
                    fact_ids = []
                    for source_id in fact.get("source_message_ids") or []:
                        try:
                            source_id = int(source_id)
                        except (TypeError, ValueError):
                            continue
                        if source_id in allowed_ids and source_id in source_ids and source_id not in fact_ids:
                            fact_ids.append(source_id)
                    if not fact_ids:
                        # 模型偶尔省略事实级证据。用字符二元组只选最相近原文，
                        # 不能把事件全部消息都标成已覆盖，否则缺失事实无法被发现。
                        value_grams = {value[index:index + 2] for index in range(max(0, len(value) - 1))}
                        ranked_sources = []
                        for source_id in source_ids:
                            source_text = next(
                                (str(row.get("content") or "") for row in messages if int(row["id"]) == source_id), ""
                            )
                            source_grams = {
                                source_text[index:index + 2] for index in range(max(0, len(source_text) - 1))
                            }
                            overlap = len(value_grams & source_grams) / max(1, min(len(value_grams), len(source_grams)))
                            ranked_sources.append((overlap, source_id))
                        best_overlap = max((row[0] for row in ranked_sources), default=0.0)
                        if best_overlap > 0:
                            fact_ids = [
                                source_id for overlap, source_id in ranked_sources
                                if overlap >= max(0.12, best_overlap * 0.75)
                            ]
                        if not fact_ids and source_ids:
                            fact_ids = [source_ids[0]]
                    facts.append({
                        "type": self._canonical_fact_type(
                            event_kind, value, str(fact.get("type") or "fact")
                        ),
                        "value": value[:500],
                        "subject_user_id": fact.get("subject_user_id"),
                        "asserted_by_user_id": fact.get("asserted_by_user_id"),
                        "occurred_at": str(fact.get("occurred_at") or "")[:32],
                        "source_message_ids": fact_ids,
                    })
                if not facts:
                    facts = [{
                        "type": event_kind,
                        "value": summary[:500],
                        "subject_user_id": None,
                        "asserted_by_user_id": None,
                        "occurred_at": str(item.get("event_date") or "")[:32],
                        "source_message_ids": source_ids,
                    }]
                event = {
                    "title": str(item.get("title") or summary[:24])[:200],
                    "summary": summary[:2000],
                    "category": category,
                    "event_kind": event_kind,
                    "event_key": str(item.get("event_key") or item.get("title") or summary[:24]).strip()[:160],
                    "entities": entities,
                    "facts": facts,
                    "state": state,
                    "event_date": str(item.get("event_date") or "")[:32],
                    "event_end": str(item.get("event_end") or "")[:32],
                    "started_at": str(item.get("started_at") or item.get("event_date") or "")[:32],
                    "resolved_at": str(item.get("resolved_at") or item.get("event_end") or "")[:32],
                    "location": str(item.get("location") or "")[:100],
                    "emotion": str(item.get("emotion") or "")[:30],
                    "tags": [str(x)[:30] for x in (item.get("tags") or [])][:8],
                    "importance": self._unit_float(item.get("importance"), 0.5),
                    "confidence": self._unit_float(item.get("confidence"), 0.5),
                    "source_message_ids": source_ids,
                }
                if self._has_long_term_value(event, messages):
                    events.append(event)
            # 在线模型即使二次检查后仍返回空，也不能再把整批信号拼成一条兜底记忆；
            # 那会把不同日期、不同主题的事件静默合并。离线模式仍保留保守规则兜底。
            events = self._attach_uncovered_context_facts(events, messages)
            events = self._verify_fact_completeness(events, messages)
            return self._split_incoherent_events(events, messages)
        except Exception:
            logger.exception("Memory event extraction failed; keeping the sync cursor for retry")
            raise

    @staticmethod
    def _is_routine_context(text: str) -> bool:
        normalized = re.sub(r"[\s，。！？、,.!?]", "", str(text or "")).lower()
        routine_patterns = (
            "我到家以后再给你发消息", "到家以后再给你发消息", "到家再给你发消息",
            "我到家后再给你发消息", "到家后再给你发消息", "晚饭先不用等我",
            "我晚点再回复你", "晚一点再回复你",
        )
        return any(pattern in normalized for pattern in routine_patterns)

    @staticmethod
    def _canonical_fact_type(event_kind: str, value: str, suggested: str = "fact") -> str:
        """把模型自由命名的事实收敛到按事件类型定义的固定槽位。"""
        text = f"{suggested} {value}".lower()
        kind = (event_kind or "fact").lower()
        rules = {
            "trip": (
                ("meal", ("早餐", "午饭", "晚饭", "夜宵", "餐食", "吃了", "喝了")),
                ("completion", ("结束", "返程", "回到家", "回家", "回来")),
                ("destination", ("抵达", "到达", "目的地", "destination", "arrival")),
                ("activity", ("去了", "逛了", "散步", "拍照", "参观", "体验", "activity")),
            ),
            "preference": (
                ("current_preference", ("现在", "当前", "改为", "选择", "新偏好", "current")),
                ("previous_preference", ("以前", "原来", "过去", "旧偏好", "previous")),
                ("preference_topic", ("主题", "偏好项", "topic")),
            ),
            "plan": (
                ("cancellation_reason", ("原因", "冲突", "来不了", "cancellation_reason")),
                ("plan_status", ("取消", "改期", "完成", "不去了", "status")),
                ("plan_intent", ("计划", "约好", "报名", "预订", "intent")),
            ),
            "conflict": (
                ("agreement", ("约定", "共识", "以后", "轮值", "agreement")),
                ("resolution", ("和好", "道歉", "说清楚", "解决", "resolution")),
                ("conflict_reason", ("因为", "矛盾", "争执", "吵架", "不开心", "reason")),
            ),
            "reconciliation": (
                ("agreement", ("约定", "共识", "以后", "轮值", "agreement")),
                ("resolution", ("和好", "道歉", "说清楚", "解决", "resolution")),
                ("conflict_reason", ("因为", "矛盾", "争执", "吵架", "不开心", "reason")),
            ),
        }
        allowed = {item[0] for item in rules.get(kind, ())}
        normalized = re.sub(r"[^a-z0-9_]+", "_", suggested.lower()).strip("_")[:40]
        if normalized in allowed:
            return normalized
        for fact_type, markers in rules.get(kind, ()):
            if any(marker in text for marker in markers):
                return fact_type
        return normalized if normalized in allowed else (normalized or "fact")

    @classmethod
    def _attach_uncovered_context_facts(cls, events: List[Dict], messages: List[Dict]) -> List[Dict]:
        """按固定槽位补齐原始证据；只有同日、邻近且目标唯一时才回填。"""
        if not events:
            return events
        message_by_id = {int(item["id"]): item for item in messages}
        covered_slots = {
            (int(source_id), str(fact.get("type") or "fact"))
            for event in events
            for fact in event.get("facts", [])
            for source_id in fact.get("source_message_ids", [])
        }
        fact_signals = (
            ("meal", ("早餐", "午饭", "晚饭", "晚餐", "夜宵", "晚上吃", "吃的是", "吃了", "喝了", "点了", "餐厅"), {"trip", "date", "activity"}),
            ("destination", ("抵达", "到达", "到了", "我们到", "出发去"), {"trip"}),
            ("activity", ("去了", "逛了", "散步", "拍照", "参观", "看了", "体验了"), {"trip", "date", "activity"}),
            ("completion", ("旅行结束", "返程", "回到家", "回家了", "回来了"), {"trip", "date", "activity"}),
            ("agreement", ("约定", "共识", "以后", "办法", "轮值"), {"conflict", "reconciliation"}),
            ("resolution", ("和好", "道歉", "说清楚", "说开了", "解决"), {"conflict", "reconciliation"}),
            ("conflict_reason", ("吵架", "争执", "矛盾", "闹别扭", "不开心"), {"conflict", "reconciliation"}),
            ("plan_status", ("取消", "改期", "不去了", "完成了", "已经去了"), {"plan"}),
            ("current_preference", ("现在改", "现在选择", "不再", "以后不要", "明确选择"), {"preference"}),
            ("previous_preference", ("以前", "原来一直", "过去一直"), {"preference"}),
        )

        def message_date(item: Dict):
            try:
                return str(item.get("created_at") or "")[:10]
            except Exception:
                return ""

        def target_score(event: Dict, message_id: int, text: str):
            source_ids = [int(value) for value in event.get("source_message_ids", []) if str(value).isdigit()]
            if not source_ids:
                return None
            distance = min(abs(message_id - value) for value in source_ids)
            if distance > 30:
                return None
            evidence_dates = {message_date(message_by_id[value]) for value in source_ids if value in message_by_id}
            current_date = message_date(message_by_id[message_id])
            if current_date and evidence_dates and current_date not in evidence_dates:
                return None
            anchors = [str(event.get("event_key") or ""), str(event.get("title") or "")]
            anchors.extend(str(value) for value in event.get("entities", []))
            lexical = sum(1 for value in anchors if len(value.strip()) >= 2 and value.strip().lower() in text.lower())
            return lexical * 10 - distance

        for message in messages:
            message_id = int(message["id"])
            text = re.sub(r"\s+", " ", str(message.get("content") or "")).strip()
            if not text or cls._is_routine_context(text):
                continue
            matched_rows = [row for row in fact_signals if any(marker in text for marker in row[1])]
            if not matched_rows:
                continue
            for fact_type, _, compatible_kinds in matched_rows:
                compatible = [event for event in events if event.get("event_kind") in compatible_kinds]
                if not compatible:
                    continue
                ranked = sorted(
                    ((target_score(event, message_id, text), event) for event in compatible),
                    key=lambda row: row[0] if row[0] is not None else -10**9,
                    reverse=True,
                )
                ranked = [row for row in ranked if row[0] is not None]
                if not ranked:
                    continue
                # 没有主题词支撑时，只允许唯一的最近事件接收补漏，避免跨事件挂靠。
                if len(ranked) > 1 and ranked[0][0] <= 0:
                    continue
                target = ranked[0][1]
                canonical_type = cls._canonical_fact_type(target.get("event_kind", ""), text, fact_type)
                if (message_id, canonical_type) in covered_slots:
                    continue
                target.setdefault("facts", []).append({
                    "type": canonical_type,
                    "value": text[:500],
                    "subject_user_id": None,
                    "asserted_by_user_id": message.get("sender_id"),
                    "occurred_at": str(message.get("created_at") or "")[:32],
                    "source_message_ids": [message_id],
                })
                target.setdefault("source_message_ids", []).append(message_id)
                target["source_message_ids"] = list(dict.fromkeys(target["source_message_ids"]))
                covered_slots.add((message_id, canonical_type))
        return events

    def _verify_fact_completeness(self, events: List[Dict], messages: List[Dict]) -> List[Dict]:
        """按证据中真实出现的槽位做完整性复核；缺槽时整批只补抽一次。"""
        if not events:
            return events
        message_map = {int(item["id"]): item for item in messages}
        slot_signals = {
            "trip": {
                "destination": ("抵达", "到达", "到了", "我们到", "出发去"),
                "activity": ("去了", "逛了", "散步", "拍照", "参观", "体验"),
                "meal": ("早餐", "午饭", "晚饭", "晚餐", "夜宵", "晚上吃", "吃的是", "吃了", "喝了"),
                "completion": ("旅行结束", "返程", "回到家", "回家了", "回来了"),
            },
            "preference": {
                "previous_preference": ("以前", "原来一直", "过去一直"),
                "current_preference": ("现在改", "现在选择", "明确选择", "不再", "以后不要"),
            },
            "plan": {
                "plan_intent": ("计划", "约好", "报名", "预订", "下个月", "下周", "明年"),
                "plan_status": ("取消", "改期", "不去了", "完成了", "已经去了"),
                "cancellation_reason": ("原因", "时间冲突", "临时有工作", "来不了"),
            },
            "conflict": {
                "conflict_reason": ("吵架", "争执", "矛盾", "闹别扭", "不开心"),
                "resolution": ("和好", "道歉", "说清楚", "说开了"),
                "agreement": ("约定", "共识", "以后按", "轮值"),
            },
            "reconciliation": {
                "conflict_reason": ("吵架", "争执", "矛盾", "闹别扭", "不开心"),
                "resolution": ("和好", "道歉", "说清楚", "说开了"),
                "agreement": ("约定", "共识", "以后按", "轮值"),
            },
        }
        missing_by_event = {}
        evidence_ids_by_event = {}
        for index, event in enumerate(events):
            kind = str(event.get("event_kind") or "")
            schema = slot_signals.get(kind, {})
            if not schema:
                continue
            source_ids = [int(value) for value in event.get("source_message_ids", []) if str(value).isdigit()]
            source_dates = {
                str(message_map[value].get("created_at") or "")[:10]
                for value in source_ids if value in message_map
            }
            evidence = [
                item for item in messages
                if not source_dates or str(item.get("created_at") or "")[:10] in source_dates
            ]
            evidence_ids_by_event[index] = {int(item["id"]) for item in evidence}
            evidence_text = " ".join(
                str(item.get("content") or "") for item in evidence
                if not self._is_routine_context(str(item.get("content") or ""))
            )
            expected = {
                slot for slot, markers in schema.items() if any(marker in evidence_text for marker in markers)
            }
            existing = {str(fact.get("type") or "") for fact in event.get("facts", [])}
            missing = sorted(expected - existing)
            if missing:
                missing_by_event[index] = missing
        if not missing_by_event or not self.available:
            for index, missing in missing_by_event.items():
                events[index]["missing_fact_slots"] = missing
            return events

        compact_events = [{
            "event_index": index,
            "event_kind": events[index].get("event_kind"),
            "event_key": events[index].get("event_key"),
            "missing_slots": missing,
            "source_message_ids": events[index].get("source_message_ids", []),
        } for index, missing in missing_by_event.items()]
        compact_messages = [{
            "id": int(item["id"]), "created_at": str(item.get("created_at") or ""),
            "content": str(item.get("content") or "")[:1000],
        } for item in messages if not self._is_routine_context(str(item.get("content") or ""))]
        system = (
            "你是事实槽位补全器。只补充missing_slots中有原始消息直接证据的事实；没有证据就不输出。"
            "不得改写事件、不得创造原因或结果。只输出JSON数组，每项为event_index和facts；"
            "facts每项只含type、value、subject_user_id、asserted_by_user_id、occurred_at、source_message_ids，"
            "type必须来自missing_slots。subject_user_id 是事实描述的人，asserted_by_user_id 是陈述者；"
            "二者只能使用输入 sender_id，无法确定事实主体时 subject_user_id 填 null。"
        )
        try:
            raw = self._chat_strict(
                [{"role": "user", "content": json.dumps({
                    "events": compact_events, "messages": compact_messages,
                }, ensure_ascii=False)}],
                system_prompt=system, temperature=0.0, max_tokens=1400,
            )
            match = re.search(r"\[[\s\S]*\]", raw)
            patches = json.loads(match.group(0) if match else raw)
            for patch in patches if isinstance(patches, list) else []:
                try:
                    index = int(patch.get("event_index"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if index not in missing_by_event or not (0 <= index < len(events)):
                    continue
                for fact in patch.get("facts", []):
                    fact_type = str(fact.get("type") or "")
                    value = str(fact.get("value") or "").strip()
                    if fact_type not in missing_by_event[index] or not value or self._is_routine_context(value):
                        continue
                    fact_ids = []
                    for source_id in fact.get("source_message_ids") or []:
                        try:
                            source_id = int(source_id)
                        except (TypeError, ValueError):
                            continue
                        if source_id in evidence_ids_by_event.get(index, set()) and source_id not in fact_ids:
                            fact_ids.append(source_id)
                    if not fact_ids:
                        continue
                    events[index].setdefault("facts", []).append({
                        "type": fact_type, "value": value[:500],
                        "subject_user_id": fact.get("subject_user_id"),
                        "asserted_by_user_id": fact.get("asserted_by_user_id"),
                        "occurred_at": str(fact.get("occurred_at") or "")[:32],
                        "source_message_ids": fact_ids,
                    })
                    events[index]["source_message_ids"] = list(dict.fromkeys(
                        list(events[index].get("source_message_ids", [])) + fact_ids
                    ))
        except Exception:
            logger.exception("Targeted memory fact completion failed; keeping verified facts")

        for index, missing in missing_by_event.items():
            existing = {str(fact.get("type") or "") for fact in events[index].get("facts", [])}
            unresolved = [slot for slot in missing if slot not in existing]
            if unresolved:
                events[index]["missing_fact_slots"] = unresolved
        return events

    @staticmethod
    def _split_incoherent_events(events: List[Dict], messages: List[Dict]) -> List[Dict]:
        """把跨越多个不相邻日期的一次性事件拆开，避免形成跨事件大记忆。"""
        message_map = {int(item["id"]): item for item in messages}
        result = []
        for event in events:
            kind = str(event.get("event_kind") or "")
            if kind in {"plan", "preference", "fact"}:
                result.append(event)
                continue
            groups = {}
            for source_id in event.get("source_message_ids", []):
                try:
                    source_id = int(source_id)
                except (TypeError, ValueError):
                    continue
                item = message_map.get(source_id)
                if not item:
                    continue
                day = str(item.get("created_at") or "")[:10]
                groups.setdefault(day, []).append(source_id)
            days = sorted(day for day in groups if day)
            if len(days) <= 1:
                result.append(event)
                continue
            try:
                parsed_days = [datetime.fromisoformat(day) for day in days]
                span_days = (max(parsed_days) - min(parsed_days)).days
            except ValueError:
                span_days = 0
            if span_days <= 2:
                result.append(event)
                continue
            for day in days:
                source_ids = groups[day]
                source_set = set(source_ids)
                split = dict(event)
                split["source_message_ids"] = source_ids
                split["facts"] = [
                    fact for fact in event.get("facts", [])
                    if set(int(value) for value in fact.get("source_message_ids", []) if str(value).isdigit()) & source_set
                ]
                split["summary"] = " ".join(
                    str(message_map[source_id].get("content") or "").strip()
                    for source_id in source_ids if source_id in message_map
                )[:2000]
                split["title"] = f"{str(event.get('title') or kind)[:160]}（{day}）"
                split["event_date"] = day
                split["started_at"] = day
                split["resolved_at"] = day if event.get("resolved_at") else ""
                split["event_key"] = f"{event.get('event_key') or kind}:{day}"
                result.append(split)
        return result

    @staticmethod
    def _has_long_term_value(event: Dict, messages: List[Dict]) -> bool:
        """对在线模型输出做保守门控，阻止即时生活状态灌入长期记忆。"""
        message_map = {int(item["id"]): str(item.get("content") or "") for item in messages}
        evidence = " ".join(message_map.get(int(item), "") for item in event.get("source_message_ids", []))
        # 门控只信原始证据。否则模型可把临时提议自行命名成“长期计划”并绕过过滤。
        text = evidence
        category = event.get("category")
        signals = {
            "preference": (
                "喜欢", "不喜欢", "偏好", "口味", "最爱", "讨厌", "不能吃", "过敏",
                "以后不要", "现在选择", "明确选择", "不再选",
            ),
            "plan": (
                "计划", "约好", "约定", "下个月", "下周", "明年", "订票", "预订",
                "报名", "取消", "改期", "不去了", "暂时没有新日期",
            ),
            "event": (
                "旅行", "旅游", "到达", "抵达", "到了", "去了", "一起去", "约会", "纪念日",
                "生日", "礼物", "吵架", "争执", "矛盾", "道歉", "和好", "求婚",
                "结婚", "搬家", "毕业", "领养", "第一次",
            ),
            "fact": (
                "生日", "纪念日", "过敏", "不能吃", "住在", "职业", "工作是", "名字是",
                "结婚", "领养", "第一次", "共同提醒",
            ),
        }
        return any(marker in text for marker in signals.get(category, ()))

    def _fallback_memory_events(self, messages: List[Dict]) -> List[Dict]:
        """模型不可用时只保留具有明显长期信息信号的对话，避免把寒暄灌入记忆。"""
        lines = [str(item.get("content") or "").strip() for item in messages]
        signals = (
            "第一次", "旅行", "旅游", "去了", "到达", "回来", "生日", "纪念日", "约会",
            "喜欢", "不喜欢", "讨厌", "爱吃", "不能吃", "以后", "计划", "想去", "一起去",
            "订票", "酒店", "电影", "礼物", "搬家", "结婚", "吵架", "和好",
            "取消", "不去了", "不去啦", "改期", "先不去",
        )
        selected = [
            (index, line)
            for index, line in enumerate(lines)
            if len(line) >= 4 and any(word in line for word in signals)
        ]
        if not selected:
            return []
        joined = " ".join(line for _, line in selected)
        extracted = self._fallback_memory_extract(joined, selected[0][1][:24])
        category = "preference" if any(word in joined for word in ("喜欢", "不喜欢", "讨厌", "爱吃", "不能吃")) else "event"
        cancelled = any(word in joined for word in ("取消", "不去了", "不去啦", "改期", "先不去"))
        planned = not cancelled and any(word in joined for word in ("以后", "计划", "想去", "一起去", "下次"))
        return [{
            **extracted,
            "category": "plan" if planned and category == "event" else category,
            "event_kind": "preference" if category == "preference" else ("plan" if planned or cancelled else "event"),
            "event_key": selected[0][1][:80],
            "entities": [],
            "facts": [{
                "type": "preference" if category == "preference" else ("plan" if planned or cancelled else "event"),
                "value": joined[:500],
                "subject_user_id": None,
                "asserted_by_user_id": None,
                "occurred_at": "",
                "source_message_ids": [int(messages[index]["id"]) for index, _ in selected],
            }],
            "state": "cancelled" if cancelled else ("planned" if planned else "completed"),
            "event_end": "",
            "started_at": "",
            "resolved_at": "",
            "confidence": 0.7,
            "source_message_ids": [int(messages[index]["id"]) for index, _ in selected],
        }]

    def summarize_memory_candidate(self, candidate: Dict, messages: List[Dict]) -> Dict:
        """仅根据已聚合证据生成一条正式记忆；不再负责从噪声中寻找事件。"""
        evidence = [{
            "id": item["id"], "created_at": str(item.get("created_at") or ""),
            "content": str(item.get("content") or "")[:1000],
        } for item in messages]
        fragments = [item for item in candidate.get("fragments", []) if isinstance(item, dict)]
        summaries = []
        for fragment in fragments:
            summary = re.sub(r"\s+", " ", str(fragment.get("summary") or "")).strip()
            if summary and summary not in summaries:
                summaries.append(summary)
        fact_values = []
        for fact in candidate.get("facts", []):
            value = re.sub(r"\s+", " ", str(fact.get("value") or "")).strip()
            if value and value not in fact_values:
                fact_values.append(value)
        fallback_text = "；".join(summaries) or "；".join(fact_values)
        if not fallback_text:
            fallback_text = " ".join(item["content"] for item in evidence)
        fragment_title = next((
            str(item.get("title") or "").strip() for item in reversed(fragments)
            if str(item.get("title") or "").strip()
        ), "")
        location = next((
            str(item.get("location") or "").strip() for item in reversed(fragments)
            if str(item.get("location") or "").strip()
        ), "")
        fallback = {
            "title": fragment_title or candidate.get("title_hint") or fallback_text[:24] or "共同记忆",
            "summary": fallback_text[:2000],
            "location": location[:100], "emotion": "", "tags": [candidate.get("event_kind", "event")],
            "importance": 0.6,
        }
        if not self.available or not self.memory_summary_with_model:
            return fallback
        system = (
            "你是长期记忆总结器。输入已经完成事件聚合，不要筛选或拆分，只生成一条完整记忆。"
            "只能使用原始证据和结构化facts；必须保留facts中的时间、地点、活动、餐食、状态变化和解决办法。"
            "不得删掉任何仍有效的原子事实；遇到新旧偏好时应明确当前值和旧值。"
            "summary必须逐项保留facts的具体value，尤其是餐食名称、偏好新值、取消原因和冲突后的具体约定；"
            "不能把‘建立家务轮值表’改写成‘找到相处方式’这类泛化表达。"
            "不得补充证据中没有的人名、原因、结果或情绪。只输出JSON对象，字段为"
            "title、summary、location、emotion、tags、importance。summary不超过240字。"
        )
        prompt = json.dumps({"candidate": candidate, "evidence": evidence}, ensure_ascii=False)
        raw = self._chat_strict(
            [{"role": "user", "content": prompt}], system, temperature=0.0, max_tokens=700
        )
        match = re.search(r"\{[\s\S]*\}", raw)
        data = json.loads(match.group(0) if match else raw)
        return {
            "title": str(data.get("title") or fallback["title"])[:200],
            "summary": str(data.get("summary") or fallback["summary"])[:2000],
            "location": str(data.get("location") or "")[:100],
            "emotion": str(data.get("emotion") or "")[:30],
            "tags": [str(value)[:30] for value in (data.get("tags") or [])][:8],
            "importance": self._unit_float(data.get("importance"), 0.6),
        }

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

    def memory_answer(
        self, question: str, context: str, history: List[Dict] | None = None, strict: bool = False,
        viewer_user_id: int | None = None,
    ) -> str:
        if context.strip() == "没有找到相关共同记忆。":
            return "目前没有找到相关记录，所以我无法确认这件事。"
        conflict_answer = self._deterministic_conflict_answer(question, context)
        if conflict_answer:
            return self._sanitize_memory_answer(conflict_answer, question)
        structured_answer = self._deterministic_structured_answer(question, context, viewer_user_id)
        if structured_answer:
            return self._sanitize_memory_answer(structured_answer, question)
        system = (
            "你是专属于一对情侣的共同记忆助手。只能依据给出的共同记忆回答，绝对不可编造。"
            "请像熟悉他们故事的温暖朋友一样直接回答：自然、亲切、简洁，不过度煽情，也不要使用客服腔。"
            "不要展示检索过程，不要提到来源、片段、编号或共同记忆库，不要使用[1][2]等引用标记。"
            "记录时间不等于事件发生时间；用户询问具体日期而记录中没有明确日期时，要温和地说明目前只能确认事件，无法确认具体时间。"
            "多条记录互相矛盾时应指出暂时无法确定，并邀请两个人补充或确认。"
            "问题询问地点、餐食、当前偏好、取消状态或和好后的约定时，必须原样保留相关facts中的具体值，"
            "不能用‘达成共识’‘找到办法’等泛化表达替代。"
            "当共同记忆中出现agreement=具体约定时，回答必须逐字保留等号后的具体约定，不得改写。"
            "planned 只代表计划，不能回答成已经发生；uncertain 只能作为不确定线索。"
            "信息不足时，只能用第一人称说明‘我还没记住这件事’或‘目前无法确认’，并邀请用户补充；"
            "绝对不能把‘没有记录’推断成‘你们没有做过、没有收到过、没有计划过或没有发生过’。"
            "同样不能说‘后来没再提’‘一直没有重新安排’‘从未在记忆里出现’，只能说后续目前无法确认。"
            "除非用户主动询问建议，否则不要新增‘可以重新约时间’等未来行动建议。"
            "不要为了活泼添加票、交通工具、装备、价格等参考内容里没有的玩笑细节。"
            "不要进行心理诊断，也不要替用户做关系决定。回答通常控制在2到4句话。"
        )
        prompt = f"【共同记忆】\n{context}\n\n【问题】\n{question}"
        messages = (history or []) + [{"role": "user", "content": prompt}]
        if strict:
            answer = self._chat_strict(messages, system, temperature=0.1, max_tokens=1000)
        else:
            answer = self.chat(messages, system_prompt=system, temperature=0.1, max_tokens=1000)
        return self._sanitize_memory_answer(answer, question)

    @staticmethod
    def _context_line_score(question: str, line: str) -> int:
        chinese = "".join(re.findall(r"[\u4e00-\u9fa5]+", question))
        generic = {"什么", "怎么", "如何", "我们", "你们", "那次", "后来", "最后", "当前", "现在"}
        terms = {
            chinese[index:index + size]
            for size in (2, 3, 4)
            for index in range(max(0, len(chinese) - size + 1))
        } - generic
        return sum(1 for term in terms if term in line)

    @staticmethod
    def _line_facts(line: str) -> Dict[str, List[tuple[int | None, str]]]:
        facts: Dict[str, List[tuple[int | None, str]]] = {}
        for fact_type, subject, value in re.findall(
            r"(?:^|[；：])([a-zA-Z_][a-zA-Z0-9_]*)(?:@(\d+))?=([^；\n]+)", line
        ):
            facts.setdefault(fact_type, []).append((int(subject) if subject else None, value.strip()))
        return facts

    @classmethod
    def _deterministic_structured_answer(
        cls, question: str, context: str, viewer_user_id: int | None = None
    ) -> str:
        """常见事实问题直接读取结构化槽位，降低模型改写事实或张冠李戴的概率。"""
        groups = []
        if any(marker in question for marker in ("偏好", "喜欢", "口味", "选择", "爱吃", "不喜欢")):
            groups.append(("preference", ("current_preference", "previous_preference")))
        if any(marker in question for marker in ("计划", "安排", "取消", "改期", "打算", "预订")):
            groups.append(("plan", ("plan_intent", "plan_status", "cancellation_reason")))
        if any(marker in question for marker in ("旅行", "旅游", "去了哪里", "吃了什么", "吃什么", "餐", "游览", "做了什么")):
            groups.append(("trip", ("destination", "activity", "meal", "completion")))
        if not groups:
            return ""
        wanted = {fact_type for _, fact_types in groups for fact_type in fact_types}
        candidates = []
        for line in context.splitlines():
            facts = cls._line_facts(line)
            if wanted.intersection(facts):
                candidates.append((cls._context_line_score(question, line), line, facts))
        if not candidates:
            return ""
        _, _, facts = max(candidates, key=lambda row: row[0])

        if "current_preference" in facts:
            # “以后不要再按半糖准备”描述的是被废止的旧偏好，不能当成当前值。
            positive = [
                row for row in facts["current_preference"]
                if not re.search(r"(?:不要|不再|别再|停止).{0,8}(?:按|选|准备)", row[1])
            ]
            subject, value = (positive or facts["current_preference"])[-1]
            owner = "你" if viewer_user_id is not None and subject == viewer_user_id else (
                "对方" if viewer_user_id is not None and subject is not None else "记录中的偏好"
            )
            previous = [row for row in facts.get("previous_preference", []) if row[0] == subject]
            if previous:
                return f"{owner}当前的偏好是：{value}。此前记录的是：{previous[-1][1]}。"
            return f"{owner}当前的偏好是：{value}。"

        if any(key in facts for key in ("plan_intent", "plan_status", "cancellation_reason")):
            parts = []
            for key, label in (("plan_intent", "计划"), ("plan_status", "状态"), ("cancellation_reason", "原因")):
                if facts.get(key):
                    parts.append(f"{label}：{facts[key][-1][1]}")
            return "记录显示，" + "；".join(parts) + "。"

        parts = []
        for key, label in (("destination", "地点"), ("activity", "活动"), ("meal", "餐食"), ("completion", "结果")):
            if facts.get(key):
                parts.append(f"{label}：{facts[key][-1][1]}")
        return ("记录显示，" + "；".join(parts) + "。") if parts else ""

    @staticmethod
    def _deterministic_conflict_answer(question: str, context: str) -> str:
        """冲突类问题直接使用结构化槽位，避免模型泛化或遗漏具体约定。"""
        if not any(marker in question for marker in ("怎么和好", "如何和好", "闹矛盾", "吵架", "争执", "冲突")):
            return ""
        lines = [line for line in context.splitlines() if "agreement=" in line]
        if not lines:
            return ""
        chinese = "".join(re.findall(r"[\u4e00-\u9fa5]+", question))
        terms = {
            chinese[index:index + size]
            for size in (2, 3, 4)
            for index in range(max(0, len(chinese) - size + 1))
        }
        generic = {"怎么", "如何", "和好", "矛盾", "吵架", "争执", "冲突", "那次", "我们"}
        terms -= generic
        line = max(lines, key=lambda value: sum(1 for term in terms if term in value))

        def fact_value(fact_type: str) -> str:
            match = re.search(rf"(?:^|[；：]){fact_type}(?:@\d+)?=([^；\n]+)", line)
            return match.group(1).strip() if match else ""

        reason = fact_value("conflict_reason")
        resolution = fact_value("resolution")
        agreement = fact_value("agreement")
        if not agreement:
            return ""
        parts = []
        if reason:
            parts.append(f"那次是因为{reason}产生了矛盾。")
        if resolution:
            parts.append(f"后来你们{resolution}。")
        parts.append(f"最后约定：{agreement}。")
        return "".join(parts)

    @staticmethod
    def _sanitize_memory_answer(answer: str, question: str = "") -> str:
        """移除模型对记录缺失和未来安排的二次推断。"""
        text = str(answer or "").strip()
        unsupported_absence = re.compile(
            r"[^。！？\n]*(?:后来(?:也|好像)?(?:一直)?没再提过|后来(?:也|好像)?(?:一直)?没有再提过|"
            r"没有在记忆里出现过|没在记忆里出现过|从未在记忆里出现过|一直没有重新安排)[^。！？\n]*[。！？]?"
        )
        text = unsupported_absence.sub("关于后续情况，目前无法确认。", text)
        asks_advice = any(marker in question for marker in ("怎么办", "怎么做", "建议", "要不要", "可以吗"))
        if not asks_advice:
            unsolicited_advice = re.compile(
                r"(?:如果|要是)[^。！？\n]*(?:可以|不妨|建议|随时)[^。！？\n]*[。！？]?"
            )
            text = unsolicited_advice.sub("", text)
        text = re.sub(r"(?:关于后续情况，目前无法确认。\s*){2,}", "关于后续情况，目前无法确认。", text)
        return text.strip()

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
