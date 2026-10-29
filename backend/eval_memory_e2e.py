"""端到端长期记忆评测：原始聊天 -> AI 抽取 -> 检索 -> AI 回答。"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Couple, MemoryEmbeddingBucket, Message, SharedMemory, User
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "memory_e2e_eval.db"
TRUTH_PATH = DATA_DIR / "memory_e2e_ground_truth.json"
REPORT_JSON = REPORT_DIR / "memory_e2e_report.json"
REPORT_MD = REPORT_DIR / "memory_e2e_report.md"
BASELINE_JSON = REPORT_DIR / "memory_e2e_report_baseline.json"
SEED = 20261027
BATCH_SIZE = memory_service.CHAT_BATCH_SIZE
DEFAULT_CASES_PER_KIND = 8
DEFAULT_NOISE_BATCHES = 8
DEFAULT_NEGATIVE_QUESTIONS = 12
FULL_CASES_PER_KIND = 16
FULL_NOISE_BATCHES = 16
FULL_NEGATIVE_QUESTIONS = 24


EVENTS = [
    ("武汉", "东湖绿道", "藕汤"), ("重庆", "鹅岭二厂", "小面"),
    ("南京", "颐和路", "盐水鸭"), ("杭州", "九溪", "片儿川"),
    ("成都", "杜甫草堂", "甜水面"), ("厦门", "沙坡尾", "花生汤"),
    ("青岛", "小麦岛", "鲅鱼水饺"), ("苏州", "虎丘", "桂花糖粥"),
    ("长沙", "梅溪湖", "米粉"), ("西安", "城墙", "甑糕"),
    ("大理", "喜洲古镇", "乳扇"), ("泉州", "蟳埔村", "四果汤"),
    ("广州", "永庆坊", "艇仔粥"), ("北京", "景山公园", "炸酱面"),
    ("上海", "西岸美术馆", "排骨年糕"), ("昆明", "斗南花市", "烧饵块"),
]

PREFERENCES = [
    ("咖啡甜度", "半糖拿铁", "无糖燕麦拿铁"), ("火锅辣度", "中辣", "微辣"),
    ("早餐饮品", "豆浆", "热牛奶"), ("电影类型", "悬疑片", "纪录片"),
    ("周末运动", "跑步", "骑行"), ("座位位置", "靠窗", "靠过道"),
    ("蛋糕口味", "抹茶", "海盐芝士"), ("旅行节奏", "一天四个景点", "每天两个地方"),
    ("晚餐主食", "米饭", "杂粮饭"), ("奶茶配料", "珍珠", "不加小料"),
    ("音乐风格", "民谣", "轻爵士"), ("拍照风格", "胶片复古", "自然抓拍"),
    ("住宿类型", "设计酒店", "安静民宿"), ("交通方式", "网约车", "地铁优先"),
    ("花的种类", "向日葵", "洋桔梗"), ("香味偏好", "木质香", "柑橘香"),
]

PLANS = [
    "去哈尔滨看雪", "报名陶艺课", "参加城市夜跑", "周末露营",
    "看草莓音乐节", "订温泉酒店", "拍周年写真", "学习双人舞",
    "参加烘焙课", "坐夜游轮船", "去看话剧", "骑行环湖",
    "去植物园拍花", "参加读书会", "去海洋馆", "去郊外观星",
]

CONFLICTS = [
    ("忘记倒垃圾", "列了家务轮值表"), ("回消息太晚", "忙时发一句简短说明"),
    ("旅行预算超支", "单独建立旅行预算"), ("临时改变计划", "改计划前先询问"),
    ("约会迟到", "迟到十分钟就提前通知"), ("睡前一直看手机", "睡前半小时放下手机"),
    ("没有提前说加班", "确定加班后马上发消息"), ("买东西没商量", "共同用品先商量"),
    ("周末安排太满", "每周末只排一件大事"), ("说话语气太急", "情绪上来先暂停十分钟"),
    ("忘记纪念日", "把日期加入共同提醒"), ("做饭口味太辣", "做饭前确认辣度"),
    ("出门路线不同", "前一晚确认路线"), ("拍照等太久", "每次只选十张照片"),
    ("空调温度不一致", "睡觉固定二十六度"), ("玩游戏忘了时间", "设置结束闹钟"),
]

NO_ANSWER = [
    "我们有没有去南极看过企鹅？", "我生日时收到过绿色唱片机吗？",
    "我们是不是在冰岛蓝湖办过婚礼？", "我现在喜欢喝榴莲味汽水吗？",
    "去摩洛哥旅行时住的是哪家酒店？", "我们取消过热气球环球旅行吗？",
    "上次去月球吃了什么晚饭？", "我是不是最喜欢紫色玫瑰？",
    "我们因为养羊驼吵过架吗？", "共同养的金毛叫什么名字？",
    "我们去过里约热内卢几次？", "去年纪念日送的是无人机吗？",
    "我现在的早餐偏好是椰子水吗？", "我们完成过潜水证考试吗？",
    "在纽约旅行时看了哪场音乐剧？", "我们取消过沙漠骑骆驼计划吗？",
    "我最喜欢的香水是玫瑰香吗？", "我们因装修地下室和好了吗？",
    "去北海道时吃过海胆饭吗？", "我们约好明年移居火星了吗？",
    "我收到过一台复古打字机吗？", "我们在巴黎铁塔下求婚了吗？",
    "共同领养的兔子是哪一天到家的？", "我现在喜欢极限跳伞吗？",
]

CHATTER = [
    "今天地铁人不算多，我刚好有座位。", "中午的青菜面有点淡。",
    "快递已经放进柜子了。", "我把窗台擦干净了。",
    "晚上如果不累就下楼走一会儿。", "刚才开会比预计早结束。",
    "冰箱里还有两颗鸡蛋。", "今天的云看起来像一只猫。",
    "洗衣机已经停了，回去记得晾衣服。", "楼下便利店换了新的招牌。",
    "手机电量只剩三成了。", "我刚把周报发出去。",
    "今天风有一点大。", "门口的花开了两朵。",
    "晚饭先不用等我。", "我到家以后再给你发消息。",
    "水杯忘在桌上了。", "上午的事情都处理完了。",
    "外面开始下小雨。", "电梯今天稍微有点慢。",
    "我把灯关好了。", "午休只睡了十分钟。",
    "公交车刚刚到站。", "那首歌我晚点发给你。",
    "今天办公室有点冷。", "纸巾快用完了。",
]


def make_case(kind: str, index: int, date: datetime) -> dict:
    if kind == "event":
        city, place, food = EVENTS[index]
        evidence = [
            f"{date:%Y年%m月%d日}我们到{city}啦。",
            f"下午只去了{place}，在那里慢慢散步拍照。",
            f"晚上吃的是{food}，我觉得很香。",
        ]
        return {
            "id": f"event-{index:02d}", "kind": kind, "date": date, "state": "completed",
            "category": "event", "evidence": evidence,
            "required_memory": [city, place, food], "required_answer": [place, food], "forbidden_answer": [],
            "question": f"{date.year}年{date.month}月去{city}时逛了哪里，晚饭吃了什么？",
        }
    if kind == "preference":
        topic, old, new = PREFERENCES[index]
        evidence = [
            f"说到{topic}，我以前一直选{old}。",
            f"不过现在口味变了，以后不要再按{old}准备。",
            f"请记住我现在明确选择{new}。",
        ]
        return {
            "id": f"preference-{index:02d}", "kind": kind, "date": date, "state": "ongoing",
            "category": "preference", "evidence": evidence,
            "required_memory": [topic, new], "required_answer": [new], "forbidden_answer": [],
            "question": f"我现在关于{topic}的偏好是什么？",
        }
    if kind == "plan":
        plan = PLANS[index]
        evidence = [
            f"我们原来约好下个月{plan}。",
            "但那几天临时有工作，时间完全冲突。",
            f"所以这次{plan}已经取消了，暂时没有新日期。",
        ]
        return {
            "id": f"plan-{index:02d}", "kind": kind, "date": date, "state": "cancelled",
            "category": "plan", "evidence": evidence,
            "required_memory": [plan, "取消"], "required_answer": ["取消"],
            "forbidden_answer": ["已经完成", "已经去了", "如期"],
            "question": f"原来安排的“{plan}”最后怎么样了？",
        }
    topic, resolution = CONFLICTS[index]
    evidence = [
        f"昨晚我们因为{topic}吵了一架，两个人都很不开心。",
        "今天冷静下来把各自的想法说清楚了，也互相道了歉。",
        f"我们已经和好了，还一起{resolution}，以后按这个办法处理。",
    ]
    return {
        "id": f"reconciliation-{index:02d}", "kind": kind, "date": date, "state": "completed",
        "category": "event", "evidence": evidence,
        "required_memory": [topic, "和好", resolution], "required_answer": [resolution],
        "forbidden_answer": ["还没有和好", "已经分手"],
        "question": f"那次因为{topic}闹矛盾后，我们怎么和好的？",
    }


def build_messages(cases_per_kind: int = DEFAULT_CASES_PER_KIND, noise_batch_count: int = DEFAULT_NOISE_BATCHES):
    rng = random.Random(SEED)
    cases = []
    messages = []
    next_id = 1
    start = datetime(2019, 1, 6, 18, 0)
    kinds = ["event", "preference", "plan", "reconciliation"]
    for kind_index, kind in enumerate(kinds):
        for index in range(cases_per_kind):
            date = start + timedelta(days=(kind_index * cases_per_kind + index) * 37)
            case = make_case(kind, index, date)
            evidence_positions = sorted(rng.sample(range(5, 25), len(case["evidence"])))
            evidence_ids = []
            for pos in range(BATCH_SIZE):
                if pos in evidence_positions:
                    line = case["evidence"][evidence_positions.index(pos)]
                    evidence_ids.append(next_id)
                else:
                    line = CHATTER[(pos + index * 3 + kind_index * 5) % len(CHATTER)]
                messages.append({
                    "id": next_id, "couple_id": 1, "sender_id": 1 + (pos % 2),
                    "content": line, "msg_type": "text", "read_status": True,
                    "created_at": date + timedelta(minutes=pos * 2),
                })
                next_id += 1
            case["evidence_ids"] = evidence_ids
            cases.append(case)

    noise_batches = noise_batch_count
    for batch in range(noise_batches):
        date = start + timedelta(days=(len(cases) + batch) * 37)
        for pos in range(BATCH_SIZE):
            messages.append({
                "id": next_id, "couple_id": 1, "sender_id": 1 + (pos % 2),
                "content": CHATTER[(pos * 5 + batch * 7) % len(CHATTER)],
                "msg_type": "text", "read_status": True,
                "created_at": date + timedelta(minutes=pos * 2),
            })
            next_id += 1
    return messages, cases, noise_batches


def ids(value: str) -> set[int]:
    try:
        return {int(item) for item in json.loads(value or "[]")}
    except (ValueError, TypeError, json.JSONDecodeError):
        return set()


def memory_text(memory: SharedMemory) -> str:
    return f"{memory.title or ''} {memory.content or ''} {memory.location or ''}"


def make_context(sources: list[dict]) -> str:
    parts = []
    for item in sources:
        facts = "；".join(
            f"{fact.get('type', 'fact')}={fact.get('value', '')}"
            for fact in item.get("facts", []) if fact.get("value")
        )
        evidence = "；".join(f"{row['created_at']}：{row['content']}" for row in item.get("evidence", [])[:6])
        parts.append(
            f"- 事件时间：{item['event_date'] or '未知'}；状态：{item.get('memory_state') or '未知'}；"
            f"类型：{item['title']}；内容：{item['content']}"
            + (f"；已确认事实：{facts}" if facts else "")
            + (f"；原始证据：{evidence}" if evidence else "")
        )
    return "\n".join(parts) or "没有找到相关共同记忆。"


def judge_answer(question: str, context: str, answer: str, expected: str = "") -> dict:
    """第二遍模型判定只评估回答中的事实是否被上下文支持。"""
    system = (
        "你是严格的事实一致性评测器。判断回答中的每个具体事实是否都由参考内容支持，"
        "以及回答是否真正回答了问题。只输出JSON对象："
        '{"supported":true或false,"answered":true或false,"covers_expected":true或false,'
        '"unsupported_claims":["..."]}。'
        "语气、概括和同义改写不算错误；新增的人名、地点、日期、状态、原因、结果算无依据。"
        "当参考内容明确表示没有找到相关记忆时，回答中的‘没记住’、‘未记录’、‘无法确认’"
        "属于有依据的认知状态，不算新增事实；‘如果发生过请告诉我’等条件句或邀请也不算事实断言。"
        "但是，不能把缺少记录推断成现实中没有发生：‘没去过’、‘没发生’、‘没约好’等否定事实，"
        "以及为了活泼而补充的具体物品、计划或经历，仍必须判为无依据。"
        "标准答案要点为‘无；应明确表示资料不足’时，只要回答清楚表达资料不足，covers_expected应为true。"
    )
    prompt = f"参考内容：\n{context}\n\n标准答案要点：{expected or '无；应明确表示资料不足'}\n\n问题：{question}\n\n回答：{answer}"
    raw = ai_service._chat_strict(
        [{"role": "user", "content": prompt}], system, temperature=0.0, max_tokens=300
    )
    try:
        match = re.search(r"\{[\s\S]*\}", raw)
        value = json.loads(match.group(0) if match else raw)
        return {
            "supported": bool(value.get("supported")), "answered": bool(value.get("answered")),
            "covers_expected": bool(value.get("covers_expected")),
            "unsupported_claims": [str(item) for item in value.get("unsupported_claims", [])],
        }
    except Exception:
        return {"supported": False, "answered": False, "covers_expected": False,
                "unsupported_claims": ["评测器输出无法解析"]}


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_report(payload: dict):
    m = payload["metrics"]
    extraction_failures = [row for row in payload["extraction_cases"] if not row["memory_correct"]]
    answer_failures = [row for row in payload["answer_cases"] if not row["answer_correct"]]
    negative_failures = [row for row in payload["negative_cases"] if not row["passed"]]
    lines = [
        "# 长期记忆端到端真实性测试报告", "", f"生成时间：{payload['generated_at']}", "",
        "## 测试链路", "",
        "原始碎片聊天 → AI事件抽取 → 独立SQLite持久化 → 语义检索 → AI最终回答 → 事实一致性复核。", "",
        "## 数据集", "",
        f"- 原始聊天：{payload['dataset']['messages']} 条",
        f"- 带标准答案的真实事件：{payload['dataset']['truth_events']} 个",
        f"- 纯闲聊批次：{payload['dataset']['noise_batches']} 批",
        f"- 正向回答问题：{payload['dataset']['positive_questions']} 个",
        f"- 无答案问题：{payload['dataset']['negative_questions']} 个",
        f"- 抽取模型：{payload['chat_model']}", f"- 向量模型：{payload['embedding_model']}", "",
    ]
    if payload.get("execution_note"):
        lines += ["## 执行状态", "", f"- {payload['execution_note']}", ""]
    lines += [
        "## 核心结果", "", "| 指标 | 结果 |", "|---|---:|",
        f"| 事件抽取召回率 | {pct(m['extraction_recall'])} |",
        f"| 抽取记忆内容正确率 | {pct(m['memory_content_accuracy'])} |",
        f"| 抽取状态正确率 | {pct(m['extraction_state_accuracy'])} |",
        f"| 抽取日期正确率 | {pct(m['extraction_date_accuracy'])} |",
        f"| 抽取类别正确率 | {pct(m['extraction_category_accuracy'])} |",
        f"| 抽取记忆精确率 | {pct(m['extraction_precision'])} |",
        f"| 单事件单记忆粒度正确率 | {pct(m['granularity_accuracy'])} |",
        f"| 纯闲聊拒绝率 | {pct(m['noise_rejection_rate'])} |",
        f"| 端到端 Recall@5 | {pct(m['retrieval_recall_at_5'])} |",
        f"| 最终答案正确率 | {pct(m['answer_accuracy'])} |",
        f"| 回答事实有据率（模型复核） | {pct(m['answer_supported_rate'])} |",
        f"| 无答案拒答率 | {pct(m['negative_abstention_rate'])} |",
        f"| 无答案最终未编造率 | {pct(m['negative_non_fabrication_rate'])} |",
        f"| 端到端中位耗时 | {m['median_answer_latency_ms']:.2f} ms |",
        "",
    ]
    if BASELINE_JSON.exists():
        baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
        lines += [
            "## 长期价值门控前后", "",
            "| 数据 | 原始宽松抽取 | 当前证据门控 |", "|---|---:|---:|",
            f"| 实际写入记忆 | {baseline['dataset']['extracted_memories']} | {payload['dataset']['extracted_memories']} |",
            f"| 无标准事件证据的多余记忆 | {baseline['dataset']['extra_memories']} | {payload['dataset']['extra_memories']} |",
            "",
            "第一轮暴露了模型会把快递、洗衣、通勤等即时状态写成长期记忆；当前门控只依据原始证据放行候选。",
            "两轮的回答判定规则随后做过校正，因此不直接比较两轮回答正确率。", "",
        ]
    lines += [
        "## 失败样例", "",
    ]
    if not extraction_failures and not answer_failures and not negative_failures and m["answer_accuracy"] == 1:
        lines.append("- 本轮没有失败样例。")
    for row in extraction_failures[:12]:
        memory_text = " ".join((row.get("memory_text") or "未抽取").split())
        lines.append(f"- 抽取失败：{row['id']}，实际记忆：{memory_text}")
    for row in answer_failures[:12]:
        lines.append(f"- 回答失败：{row['question']} → {' '.join(row['answer'].split())}")
    for row in negative_failures[:12]:
        lines.append(f"- 无答案失败：{row['question']} → {' '.join(row['answer'].split())}")
    if not payload["answer_cases"]:
        lines.append("- 在线回答明细未保留；核心指标来自最后一次完整在线运行，详见执行状态。")
    lines += [
        "", "## 判定方法", "",
        "- 抽取召回要求记忆引用了标准事件的证据消息；内容正确还要求包含标准答案中的关键实体。",
        "- 日期、类别和状态分别与标准答案严格比对；抽取精确率会惩罚从闲聊中产生的多余记忆。",
        "- 最终答案必须包含标准答案关键内容、不得采纳已作废信息，并由第二遍事实一致性评测检查新增事实。",
        "- 无答案题要求最终回答明确表示未记录或无法确认，且事实评测不发现捏造；若用相关有效记忆纠正问题中的错误前提，不算编造。", "",
        "## 适用边界", "",
        "- 这是程序合成但保持碎片聊天结构的盲测数据，不含真实用户隐私，仍需真实用户匿名样本复核。",
        "- 事实一致性复核由同一服务配置的语言模型执行，可能存在评测偏差，因此同时保留关键词和状态的确定性检查。",
        "- 本报告衡量当前固定数据集与当前模型配置，模型、提示词或阈值变化后必须重新运行。", "",
        "## 可复现文件", "",
        f"- 独立数据库：`{DB_PATH}`", f"- 标准答案：`{TRUTH_PATH}`", f"- 结构化结果：`{REPORT_JSON}`",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(resume: bool = False, rescore: bool = False, full: bool = False):
    if not ai_service.available:
        raise RuntimeError("端到端真实性评测需要可用的 AI_API_KEY，当前只能使用离线规则模板")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cases_per_kind = FULL_CASES_PER_KIND if full else DEFAULT_CASES_PER_KIND
    noise_batch_count = FULL_NOISE_BATCHES if full else DEFAULT_NOISE_BATCHES
    negative_count = FULL_NEGATIVE_QUESTIONS if full else DEFAULT_NEGATIVE_QUESTIONS
    messages, cases, noise_batches = build_messages(cases_per_kind, noise_batch_count)
    negative_questions = NO_ANSWER[:negative_count]
    if DB_PATH.exists() and not resume:
        DB_PATH.unlink()
    if resume and not DB_PATH.exists():
        raise RuntimeError(f"没有可继续的端到端数据库：{DB_PATH}")
    engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        if resume:
            stored_messages = db.query(Message).order_by(Message.id.asc()).all()
            mismatch = len(stored_messages) != len(messages)
            if not mismatch:
                mismatch = any(
                    stored.id != expected["id"]
                    or stored.sender_id != expected["sender_id"]
                    or stored.content != expected["content"]
                    or stored.created_at != expected["created_at"]
                    for stored, expected in zip(stored_messages, messages)
                )
            if mismatch:
                mode = "--full" if full else "默认减半"
                raise RuntimeError(
                    f"现有评测数据库与{mode}数据集不一致：数据库含{len(stored_messages)}条，"
                    f"本次期望{len(messages)}条。请移除 --resume/--rescore 重新运行，"
                    "或使用与该数据库相同的 --full 参数。"
                )
        else:
            db.add_all([
                User(id=1, email="e2e.a@example.test", password_hash="unused", nickname="小墨", couple_id=1),
                User(id=2, email="e2e.b@example.test", password_hash="unused", nickname="小韵", couple_id=1),
                Couple(id=1, pairing_code="E2ETEST", user1_id=1, user2_id=2, status="active"),
            ])
            db.bulk_insert_mappings(Message, messages)
            db.commit()

        TRUTH_PATH.write_text(json.dumps({
            "cases": cases, "negative_questions": negative_questions,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        previous_sync_seconds = 0.0
        if resume and REPORT_JSON.exists():
            previous_sync_seconds = float(json.loads(REPORT_JSON.read_text(encoding="utf-8")).get("sync_seconds") or 0.0)
        sync_started = time.perf_counter()
        batch_count = (memory_service.get_settings(db, 1).last_synced_message_id or 0) // BATCH_SIZE
        total_batches = len(cases) + noise_batches
        print(
            f"开始抽取：共 {total_batches} 批 / {len(messages)} 条聊天，模型 {ai_service.model}",
            flush=True,
        )
        while True:
            result = memory_service.sync_chat_events(db, 1, max_batches=1)
            batch_count += 1
            print(f"抽取进度：{min(batch_count, total_batches)}/{total_batches} 批", flush=True)
            if result["remaining_messages"] == 0:
                break
            if not result["processed_messages"]:
                raise RuntimeError(f"聊天同步中断：{memory_service.get_settings(db, 1).sync_error}")
        sync_seconds = previous_sync_seconds or (time.perf_counter() - sync_started)

        if rescore:
            for memory in db.query(SharedMemory).filter(SharedMemory.couple_id == 1).all():
                source_ids = ids(memory.source_message_ids)
                source_messages = db.query(Message).filter(Message.id.in_(source_ids)).all() if source_ids else []
                event = {
                    "title": memory.title, "summary": memory.content, "category": memory.category,
                    "state": memory.memory_state, "source_message_ids": list(source_ids),
                }
                payload = [{"id": item.id, "content": item.content} for item in source_messages]
                if not ai_service._has_long_term_value(event, payload):
                    db.query(MemoryEmbeddingBucket).filter(MemoryEmbeddingBucket.memory_id == memory.id).delete()
                    db.delete(memory)
            db.commit()

        extracted = db.query(SharedMemory).filter(SharedMemory.couple_id == 1).all()
        all_evidence_ids = {item for case in cases for item in case["evidence_ids"]}
        supported_memory_ids = {m.id for m in extracted if ids(m.source_message_ids) & all_evidence_ids}
        extraction_rows = []
        for case in cases:
            evidence = set(case["evidence_ids"])
            matches = [m for m in extracted if ids(m.source_message_ids) & evidence]
            def match_score(memory):
                text = memory_text(memory)
                return (
                    sum(term in text for term in case["required_memory"]),
                    bool(memory.event_date and memory.event_date.date() == case["date"].date()),
                    memory.memory_state == case["state"], memory.category == case["category"],
                    len(ids(memory.source_message_ids) & evidence),
                )
            best = max(matches, key=match_score, default=None)
            text = memory_text(best) if best else ""
            content_ok = bool(best) and all(term in text for term in case["required_memory"])
            date_ok = bool(best and best.event_date and best.event_date.date() == case["date"].date())
            state_ok = bool(best and best.memory_state == case["state"])
            category_ok = bool(best and best.category == case["category"])
            extraction_rows.append({
                "id": case["id"], "kind": case["kind"], "found": bool(best),
                "memory_correct": content_ok and date_ok and state_ok and category_ok,
                "content_correct": content_ok, "date_correct": date_ok, "state_correct": state_ok,
                "category_correct": category_ok, "memory_id": best.id if best else None,
                "memory_text": text[:500], "actual_state": best.memory_state if best else None,
                "actual_date": best.event_date.isoformat() if best and best.event_date else None,
                "actual_category": best.category if best else None,
            })

        while True:
            embedded = memory_service.ensure_embeddings(db, 1, limit=128)
            if embedded["remaining_embeddings"] == 0:
                break

        answer_rows = []
        latencies = []
        for index, case in enumerate(cases):
            started = time.perf_counter()
            sources = memory_service.search(db, 1, case["question"], top_k=5, user_id=1)
            context = make_context(sources)
            answer = ai_service.memory_answer(case["question"], context, [], strict=True)
            judgment = judge_answer(case["question"], context, answer, "；".join(case["required_answer"]))
            latency = (time.perf_counter() - started) * 1000
            latencies.append(latency)
            retrieved = any(set(item.get("source_message_ids") or []) & set(case["evidence_ids"]) for item in sources)
            required_ok = all(term in answer for term in case["required_answer"])
            forbidden_ok = not any(term in answer for term in case["forbidden_answer"])
            answer_correct = (
                retrieved and required_ok and forbidden_ok and judgment["supported"]
                and judgment["answered"] and judgment["covers_expected"]
            )
            answer_rows.append({
                "id": case["id"], "question": case["question"], "retrieved": retrieved,
                "required_ok": required_ok, "forbidden_ok": forbidden_ok,
                "answer_correct": answer_correct, "answer": answer,
                "judgment": judgment, "source_ids": [item["id"] for item in sources],
                "latency_ms": round(latency, 2),
            })
            if (index + 1) % 8 == 0:
                print(f"正向问答进度：{index + 1}/{len(cases)}", flush=True)

        negative_rows = []
        refusal_words = (
            "没记", "不知道", "没有找到", "无法确认", "不能确认", "暂时不清楚",
            "还没", "没有", "不是", "未在", "没在", "未出现",
        )
        for index, question in enumerate(negative_questions):
            sources = memory_service.search(db, 1, question, top_k=5, user_id=1)
            context = make_context(sources)
            answer = ai_service.memory_answer(question, context, [], strict=True)
            judgment = judge_answer(question, context, answer)
            abstained = not sources
            refused = any(word in answer for word in refusal_words)
            non_fabricated = judgment["supported"] and not judgment["unsupported_claims"]
            negative_rows.append({
                "question": question, "abstained": abstained, "refused": refused,
                "non_fabricated": non_fabricated, "passed": refused and non_fabricated,
                "answer": answer, "judgment": judgment,
                "source_ids": [item["id"] for item in sources],
            })
            if (index + 1) % 8 == 0:
                print(f"无答案问答进度：{index + 1}/{len(negative_questions)}", flush=True)

        extra_memories = [m for m in extracted if m.id not in supported_memory_ids]
        polluted_noise_batches = set()
        noise_start = len(cases) * BATCH_SIZE + 1
        for memory in extra_memories:
            for source_id in ids(memory.source_message_ids):
                if source_id >= noise_start:
                    polluted_noise_batches.add((source_id - noise_start) // BATCH_SIZE)
        total_extracted = len(extracted)
        metrics = {
            "extraction_recall": sum(r["found"] for r in extraction_rows) / len(extraction_rows),
            "memory_content_accuracy": sum(r["content_correct"] for r in extraction_rows) / len(extraction_rows),
            "extraction_state_accuracy": sum(r["state_correct"] for r in extraction_rows) / len(extraction_rows),
            "extraction_date_accuracy": sum(r["date_correct"] for r in extraction_rows) / len(extraction_rows),
            "extraction_category_accuracy": sum(r["category_correct"] for r in extraction_rows) / len(extraction_rows),
            "extraction_precision": len(supported_memory_ids) / max(1, total_extracted),
            "granularity_accuracy": sum(
                len([m for m in extracted if ids(m.source_message_ids) & set(case["evidence_ids"])]) == 1
                for case in cases
            ) / len(cases),
            "noise_rejection_rate": 1 - len(polluted_noise_batches) / noise_batches,
            "retrieval_recall_at_5": sum(r["retrieved"] for r in answer_rows) / len(answer_rows),
            "answer_accuracy": sum(r["answer_correct"] for r in answer_rows) / len(answer_rows),
            "answer_supported_rate": sum(r["judgment"]["supported"] for r in answer_rows) / len(answer_rows),
            "negative_abstention_rate": sum(r["abstained"] for r in negative_rows) / len(negative_rows),
            "negative_non_fabrication_rate": sum(r["non_fabricated"] and r["refused"] for r in negative_rows) / len(negative_rows),
            "median_answer_latency_ms": statistics.median(latencies),
        }
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "chat_model": ai_service.model, "embedding_model": ai_service.embedding_index_model,
            "sync_seconds": round(sync_seconds, 2),
            "dataset": {"messages": len(messages), "truth_events": len(cases), "noise_batches": noise_batches,
                        "positive_questions": len(cases), "negative_questions": len(negative_questions),
                        "extracted_memories": total_extracted, "extra_memories": len(extra_memories)},
            "metrics": metrics, "extraction_cases": extraction_rows,
            "answer_cases": answer_rows, "negative_cases": negative_rows,
        }
        REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(payload)
        print(json.dumps({"report": str(REPORT_MD), "dataset": payload["dataset"], "metrics": metrics,
                          "sync_seconds": payload["sync_seconds"]}, ensure_ascii=False, indent=2))
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="从独立评测库保存的同步游标继续")
    parser.add_argument("--rescore", action="store_true", help="按当前门控清理现有候选并重新执行问答")
    parser.add_argument("--full", action="store_true", help="运行原始全量数据；默认使用一半数据以节省模型额度")
    options = parser.parse_args()
    run(resume=options.resume or options.rescore, rescore=options.rescore, full=options.full)
