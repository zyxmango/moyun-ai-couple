# AI 情侣共同记忆系统

## 产品目标

将聊天、日记、相册和纪念日统一为可检索的共同记忆，让 AI 基于真实记录提供问答、回顾和每日互动，而不是成为脱离业务数据的通用聊天入口。

## 核心流程

```text
用户明确授权
  -> 按隐私开关同步聊天/日记/相册/纪念日
  -> 统一 SharedMemory 数据模型
  -> AI/规则结构化提取（pending）
  -> 用户确认（confirmed）
  -> TF-IDF 语义相似度 + 关键词 + 时间/重要度混合排序
  -> 带来源的 RAG 回答 / 共同记忆周报
```

## 安全边界

- 默认关闭共同记忆，需要用户主动开启。
- 所有同步和检索均强制使用当前 `couple_id` 过滤。
- AI 提取的派生事件默认 `pending`，用户确认后才能进入问答。
- 用户可按来源关闭同步、删除单条记忆或清空整个 AI 索引。
- 清空 AI 索引不会删除原始聊天、日记、相册或纪念日。
- 模型提示明确禁止心理诊断、感情评分和无依据编造。

## 数据模型

- `couple_ai_settings`：情侣级授权和来源开关。
- `shared_memories`：统一记忆、来源引用、时间、地点、情绪、标签和审核状态。
- `shared_memories` 同时记录 `owner_id / visibility / category / version / is_active`，用于私密过滤和偏好版本更新。
- `date_plans`：保存规划条件、生成结果和实际检索来源，支持复盘。
- `daily_questions`：每对情侣每天唯一的问题。
- `daily_answers`：每位用户的回答，双方回答完成后才互相展示。

## API

- `GET/PUT /api/ai/memory/settings`
- `POST /api/ai/memory/sync`
- `GET/DELETE /api/ai/memory`
- `POST /api/ai/memory/extract`
- `PATCH/DELETE /api/ai/memory/{id}`
- `POST /api/ai/memory/chat`
- `POST /api/ai/memory/manual`
- `POST /api/ai/memory/report`
- `GET /api/ai/memory/daily-question/today`
- `POST /api/ai/memory/daily-question/{id}/answer`
- `POST/GET /api/ai/date-plan`

## 评估

运行：

```powershell
cd backend
conda run -n couple-app python eval_memory_rag.py
```

当前 20 条虚构记忆问答离线集关注 Recall@3、MRR 和检索延迟。该结果只用于回归验证；后续增加困难负样本、权限泄漏率、来源忠实度、拒答率、Token 和成本指标。
