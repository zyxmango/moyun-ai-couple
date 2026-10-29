# AI 情侣共同记忆系统

## 产品目标

将聊天、日记、相册和纪念日统一为可检索的共同记忆，让 AI 基于真实记录提供问答、回顾和每日互动，而不是成为脱离业务数据的通用聊天入口。

## 核心流程

```text
用户明确授权
  -> 原始聊天只保存在 messages
  -> 持久化游标按 ID 分批追赶新增聊天
  -> 连续对话抽取事件候选和带来源的原子事实
  -> 按事件类型的固定事实槽位检查原始证据并补齐遗漏
  -> 按稳定主题身份、地点和时间硬边界合并候选
  -> 程序状态机确定完成/取消/和好/偏好版本边界
  -> 原子事实物化为事件记忆并关联原始 message id
  -> 持久化语义向量与多路 LSH 候选桶
  -> 权限过滤后召回语义候选并进行精确余弦排序
  -> Top K 事件按需回查原文并生成有依据的回答
```

### 事件边界与事实完整性

- 聊天片段和事件生命周期分别处理：一次对话结束不代表计划或偏好结束，后续状态通过稳定 `event_key` 更新原事件。
- 旅行事实槽位为 `destination/activity/meal/completion`；偏好为 `preference_topic/previous_preference/current_preference`；计划为 `plan_intent/plan_status/cancellation_reason`；冲突与和好为 `conflict_reason/resolution/agreement`。
- 每个事实单独保存证据消息 ID。模型没有返回事实级证据时，只关联文本最相近的原文，不能默认覆盖整段聊天。
- 补漏只允许挂到同日、相邻且目标唯一的兼容事件；跨日期或存在两个等距候选时保持未关联，禁止猜测。
- 计划和偏好只有稳定主题相同才能跨日期合并；旅行、活动和冲突默认把日期放入事件键。闲聊套话不能作为事件身份。
- 在线模型返回空数组时只进行一次受约束复查；复查仍为空就不写记忆，禁止把整批规则信号拼成一条“大记忆”。
- 摘要和最终回答必须保留结构化事实的具体值，缺少字段时明确说明无法确认，不能用泛化表达替代具体约定。

## 安全边界

- 默认关闭共同记忆，需要用户主动开启。
- 所有同步和检索均强制使用当前 `couple_id` 过滤。
- 明确且有来源证据的事件自动进入问答；低置信度内容标记为 `uncertain`，不作为确定事实检索。
- 用户无需逐条审核，但可随时查看、修改或删除自动整理结果。
- 用户可按来源关闭同步、删除单条记忆或清空整个 AI 索引。
- 清空 AI 索引不会删除原始聊天、日记、相册或纪念日。
- 模型提示明确禁止心理诊断、感情评分和无依据编造。

## 数据模型

- `couple_ai_settings`：情侣级授权和来源开关。
- `couple_ai_settings.last_synced_message_id`：聊天整理游标；只有整批成功后才推进，失败后可重试。
- `memory_candidates`：跨批次聚合的事件候选，保存事件键、类型、原子事实和全部证据消息 ID。
- `shared_memories`：事件级记忆、来源消息 ID、时间、状态、置信度、地点、情绪和标签。
- `shared_memories.facts`：结构化原子事实数组，每项保存 `type/value/occurred_at/source_message_ids`；摘要遗漏时事实仍然保留。
- `shared_memories.event_key/event_kind`：限制相似事件合并；一次性活动把日期纳入事件键。
- `shared_memories.valid_from/valid_to`：偏好版本有效期；“当前偏好”只使用仍有效的版本。
- `memory_event_history`：保存事件状态、摘要和事实版本，更新时不覆盖历史证据。
- `shared_memories.embedding_*`：持久化的归一化语义向量及模型版本；内容变化后自动失效并重建。
- `memory_embedding_buckets`：按情侣和模型隔离的多路 LSH 索引，数据量较大时避免扫描全部向量。
- `shared_memories` 同时记录 `owner_id / visibility / category / version / is_active`，用于私密过滤和偏好版本更新。
- `date_plans`：保存规划条件、生成结果和实际检索来源，支持复盘。
- `daily_questions`：每对情侣每天唯一的问题。
- `daily_answers`：每位用户的回答，双方回答完成后才互相展示。

## API

- `GET/PUT /api/ai/memory/settings`
- `POST /api/ai/memory/sync`
- `GET/DELETE /api/ai/memory`
- `POST /api/ai/memory/extract`（兼容入口，触发自动增量整理，不再产生待确认项）
- `PATCH/DELETE /api/ai/memory/{id}`
- `POST /api/ai/memory/chat`
- `POST /api/ai/memory/manual`
- `POST /api/ai/memory/report`
- `GET /api/ai/memory/daily-question/today`
- `POST /api/ai/memory/daily-question/{id}/answer`
- `POST/GET /api/ai/date-plan`

## 评估

单元与边界测试：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

在线单例端到端验证：

```powershell
.\.venv\Scripts\python.exe verify_memory_pipeline_single.py
```

完整真实性评测：

```powershell
.\.venv\Scripts\python.exe eval_memory_e2e.py
```

默认节省额度评测覆盖 1,200 条碎片聊天、32 个标准事件、8 批纯闲聊、32 个改写问题和 12 个无答案问题，四类事件保持均衡。需要复跑原始规模时使用：

```powershell
.\.venv\Scripts\python.exe eval_memory_e2e.py --full
```

两种规模均统计抽取内容、日期、状态、Recall@5、回答正确率、来源忠实度和拒答率。

`qwen3.8-max` 默认会开启高强度思考。共同记忆抽取是结构化任务，项目默认设置
`AI_ENABLE_THINKING=false`，并直接使用已抽取的结构化事实生成正式记忆，避免为每条事件
再调用一次模型润色。需要实验模型摘要时可设置 `AI_MEMORY_SUMMARY_WITH_MODEL=true`。

## 语义索引

- 在线环境通过 `AI_EMBEDDING_MODEL` 使用 OpenAI 兼容的 embedding 接口。DashScope 默认使用 `text-embedding-v3`，OpenAI 默认使用 `text-embedding-3-small`。
- 无模型凭据时使用确定性的本地字符哈希向量，保证离线演示和测试可运行；该降级只提供词形相似度，不等同于在线语义模型。
- 新增和修改的记忆增量写入向量与四路 LSH 桶。模型名称变化时，后台会分批重建，不需要清空记忆。
- 小规模记忆直接对所有持久化向量精排；超过阈值后通过 LSH 多探针和关键词共同召回，再做精确余弦排序。
