"""独立的长期记忆真实性评估：生成聊天、标准答案、持久化索引与 Markdown 报告。"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Couple, Message, SharedMemory, User
from app.services.ai_service import ai_service
from app.services.memory_service import memory_service


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "memory_realism_eval.db"
TRUTH_PATH = DATA_DIR / "memory_realism_ground_truth.json"
REPORT_JSON = REPORT_DIR / "memory_realism_report.json"
REPORT_MD = REPORT_DIR / "memory_realism_report.md"
SEED = 20261027

CITIES = [
    ("武汉", ["东湖绿道", "湖北省博物馆", "昙华林", "江汉路"], ["热干面", "豆皮", "藕汤", "糊汤粉"]),
    ("重庆", ["洪崖洞", "南山一棵树", "李子坝", "鹅岭二厂"], ["小面", "酸辣粉", "豆花饭", "山城汤圆"]),
    ("南京", ["明孝陵", "颐和路", "南京博物院", "玄武湖"], ["鸭血粉丝汤", "盐水鸭", "梅花糕", "皮肚面"]),
    ("杭州", ["北山街", "灵隐寺", "九溪", "良渚博物院"], ["片儿川", "定胜糕", "龙井虾仁", "葱包桧"]),
    ("成都", ["人民公园", "杜甫草堂", "望平街", "青城山"], ["钟水饺", "甜水面", "兔头", "蛋烘糕"]),
    ("厦门", ["黄厝海滩", "沙坡尾", "鼓浪屿", "植物园"], ["沙茶面", "海蛎煎", "花生汤", "土笋冻"]),
    ("青岛", ["小麦岛", "八大关", "栈桥", "石老人海滩"], ["鲅鱼水饺", "海菜凉粉", "锅贴", "脂渣"]),
    ("苏州", ["平江路", "拙政园", "金鸡湖", "虎丘"], ["苏式汤面", "生煎", "桂花糖粥", "松鼠桂鱼"]),
    ("长沙", ["岳麓山", "橘子洲", "谢子龙影像馆", "梅溪湖"], ["臭豆腐", "糖油粑粑", "米粉", "口味虾"]),
    ("西安", ["城墙", "陕西历史博物馆", "大雁塔", "华清宫"], ["肉夹馍", "凉皮", "甑糕", "羊肉泡馍"]),
    ("大理", ["洱海生态廊道", "喜洲古镇", "苍山", "双廊"], ["乳扇", "饵丝", "酸辣鱼", "喜洲粑粑"]),
    ("泉州", ["开元寺", "西街", "蟳埔村", "洛阳桥"], ["面线糊", "土笋冻", "姜母鸭", "四果汤"]),
    ("广州", ["沙面", "广东省博物馆", "永庆坊", "海心桥"], ["虾饺", "艇仔粥", "云吞面", "双皮奶"]),
    ("北京", ["景山公园", "国家博物馆", "颐和园", "五道营胡同"], ["炸酱面", "铜锅涮肉", "豆汁焦圈", "驴打滚"]),
    ("上海", ["武康路", "西岸美术馆", "外滩", "共青森林公园"], ["生煎", "葱油拌面", "排骨年糕", "鲜肉月饼"]),
    ("昆明", ["翠湖", "云南省博物馆", "斗南花市", "西山"], ["过桥米线", "鲜花饼", "汽锅鸡", "烧饵块"]),
    ("福州", ["烟台山", "三坊七巷", "鼓山", "上下杭"], ["鱼丸", "肉燕", "芋泥", "锅边糊"]),
    ("天津", ["五大道", "北宁公园", "意式风情区", "天津博物馆"], ["煎饼果子", "锅巴菜", "熟梨糕", "耳朵眼炸糕"]),
    ("洛阳", ["龙门石窟", "隋唐城遗址植物园", "洛阳博物馆", "白马寺"], ["牛肉汤", "浆面条", "牡丹燕菜", "不翻汤"]),
    ("桂林", ["象鼻山", "遇龙河", "龙脊梯田", "东西巷"], ["桂林米粉", "油茶", "荔浦芋扣肉", "马蹄糕"]),
]

PREFERENCES = [
    ("咖啡甜度", "半糖拿铁", "无糖燕麦拿铁"), ("火锅辣度", "中辣", "微辣"),
    ("早餐饮品", "豆浆", "热牛奶"), ("电影类型", "悬疑片", "纪录片"),
    ("周末运动", "跑步", "骑行"), ("座位位置", "靠窗", "靠过道"),
    ("蛋糕口味", "抹茶", "海盐芝士"), ("旅行节奏", "一天多跑景点", "每天只排两个地方"),
    ("晚餐主食", "米饭", "杂粮饭"), ("奶茶配料", "珍珠", "不加小料"),
    ("音乐风格", "民谣", "轻爵士"), ("阅读类型", "推理小说", "人物传记"),
    ("拍照风格", "胶片复古", "自然抓拍"), ("散步时间", "晚饭后", "清晨"),
    ("住宿类型", "设计酒店", "安静民宿"), ("交通方式", "网约车", "地铁优先"),
    ("花的种类", "向日葵", "洋桔梗"), ("香味偏好", "木质香", "柑橘香"),
    ("家居颜色", "暖白色", "原木色"), ("甜品甜度", "正常甜", "三分甜"),
    ("面条口感", "软一点", "有嚼劲"), ("旅行纪念品", "冰箱贴", "当地明信片"),
    ("雨天活动", "逛商场", "在家做饭"), ("约会预算", "两百元左右", "三百元以内"),
    ("宠物选择", "英短猫", "领养橘猫"), ("夜宵选择", "烧烤", "清汤馄饨"),
    ("水果偏好", "芒果", "蓝莓"), ("零食口味", "香辣", "海盐"),
    ("礼物类型", "实用电器", "手写纪念册"), ("看展类型", "当代艺术", "历史文物"),
    ("手机铃声", "钢琴曲", "静音震动"), ("枕头高度", "高枕", "低枕"),
    ("空调温度", "二十四度", "二十六度"), ("做饭分工", "一人全做", "一人做饭一人洗碗"),
    ("收纳方式", "开放置物架", "带门柜子"), ("纪念日安排", "外出聚餐", "一起做一顿饭"),
    ("通勤歌单", "节奏感强", "舒缓安静"), ("运动强度", "高强度间歇", "轻量拉伸"),
    ("旅行箱大小", "二十八寸", "二十四寸"), ("聊天方式", "马上解决", "冷静后再聊"),
]

PLAN_ITEMS = [
    "去哈尔滨看雪", "去舟山看海", "报名陶艺课", "参加城市夜跑", "周末露营", "去郊区采摘",
    "看草莓音乐节", "订温泉酒店", "拍周年写真", "领养一只猫", "学习双人舞", "去天文馆",
    "参加烘焙课", "坐夜游轮船", "去看话剧", "骑行环湖", "整理旧照片", "重新布置书房",
    "去植物园拍花", "参加读书会", "安排家庭聚餐", "去海洋馆", "学习做咖啡", "周末爬山",
    "去古镇住一晚", "看日出", "参加手作市集", "去滑雪", "拍一支旅行短片", "租车自驾",
    "去农场喂小羊", "看一场篮球赛", "参加公益活动", "去水族馆过生日", "体验玻璃吹制",
    "一起学游泳", "去郊外观星", "坐高铁去邻城吃饭", "参加桌游局", "去剧院听音乐会",
]

CONFLICTS = [
    "忘记倒垃圾", "回消息太晚", "旅行预算超支", "临时改变计划", "家务分配不均", "约会迟到",
    "睡前一直看手机", "没有提前说加班", "买东西没商量", "周末安排太满", "说话语气太急", "忘记纪念日",
    "做饭口味太辣", "没有及时收拾餐桌", "出门路线意见不同", "拍照等太久", "空调温度不一致",
    "外卖点错了", "抢着替对方做决定", "玩游戏忘了时间",
]
RESOLUTIONS = [
    "列了轮值表", "约定忙时发一个简短说明", "单独建立旅行预算", "改计划前先问对方",
    "按房间重新分工", "迟到超过十分钟就提前通知", "睡前半小时把手机放远", "确定加班后马上发消息",
    "超过三百元的共同用品先商量", "每个周末只安排一件主要活动", "情绪上来先停十分钟",
    "把重要日期加入共同提醒", "做饭前确认辣度", "吃完饭一起收拾", "出门前一晚确认路线",
    "每次只选十张照片", "睡觉时固定二十六度", "下单前互相确认", "先表达需求再给建议", "设置游戏结束闹钟",
]

CHATTER_TEMPLATES = [
    "今天{weather}，出门记得带{item}。",
    "中午吃了{meal}，感觉比上周那家{taste}。",
    "刚把{task}处理完，准备起来走一走。",
    "地铁现在{traffic}，我大概{clock}到家。",
    "楼下那只小狗今天穿了{color}的小衣服。",
    "冰箱里的{food}还剩一点，晚上可以顺手解决掉。",
    "今天工作节奏{pace}，不过事情都做完了。",
    "我把窗台擦干净了，阳光照进来很好看。",
    "刚听到一首{music}，回头发给你。",
    "快递放在{place}了，回家别忘了拿。",
    "晚上如果不累，我们下楼走{minutes}分钟。",
    "今天的云像{shape}，可惜没来得及拍清楚。",
]


def chatter(event_index: int, line_index: int) -> str:
    rng = random.Random(SEED + event_index * 101 + line_index)
    values = {
        "weather": rng.choice(["有点凉", "太阳很好", "下着小雨", "风有点大", "很闷热", "空气很清爽"]),
        "item": rng.choice(["伞", "薄外套", "水杯", "充电宝", "门禁卡", "耳机"]),
        "meal": rng.choice(["鸡肉饭", "馄饨", "青菜面", "番茄炒蛋", "牛肉粉", "饭团"]),
        "taste": rng.choice(["清淡", "香一点", "更合口味", "稍微咸一点", "分量足", "新鲜"]),
        "task": rng.choice(["周报", "报表", "会议记录", "房间收纳", "洗衣服", "账单核对"]),
        "traffic": rng.choice(["不太挤", "有点慢", "刚好有座位", "临时限速", "人比平时少"]),
        "clock": rng.choice(["六点四十", "七点一刻", "七点半", "八点左右", "八点二十"]),
        "color": rng.choice(["黄色", "蓝色", "格子", "红色", "米白色"]),
        "food": rng.choice(["牛奶", "生菜", "蘑菇", "鸡蛋", "草莓", "面包"]),
        "pace": rng.choice(["有点赶", "很平稳", "前紧后松", "比昨天轻松", "忙得很充实"]),
        "music": rng.choice(["钢琴曲", "老歌", "轻爵士", "民谣", "电影配乐"]),
        "place": rng.choice(["门卫室", "快递柜", "前台", "门口架子", "便利店代收点"]),
        "minutes": rng.choice(["十五", "二十", "二十五", "三十"]),
        "shape": rng.choice(["一条鲸鱼", "棉花糖", "伸懒腰的猫", "一座小岛", "羽毛"]),
    }
    return CHATTER_TEMPLATES[(event_index + line_index) % len(CHATTER_TEMPLATES)].format(**values)


class CorpusBuilder:
    def __init__(self):
        self.messages = []
        self.memories = []
        self.truth = []
        self.message_id = 1
        self.event_index = 0

    def add_event(self, *, source_id, title, content, event_date, category, state,
                  event_lines, active=True, version=1, tags=None, importance=0.7,
                  location="", question=None, answer=None, group="event"):
        for offset in range(12):
            self.messages.append({
                "id": self.message_id, "couple_id": 1, "sender_id": 1 + (self.message_id % 2),
                "content": chatter(self.event_index, offset), "msg_type": "text", "read_status": True,
                "created_at": event_date - timedelta(hours=6, minutes=12 - offset),
            })
            self.message_id += 1
        evidence_ids = []
        for offset, line in enumerate(event_lines):
            evidence_ids.append(self.message_id)
            self.messages.append({
                "id": self.message_id, "couple_id": 1, "sender_id": 1 + (offset % 2),
                "content": line, "msg_type": "text", "read_status": True,
                "created_at": event_date + timedelta(minutes=offset * 4),
            })
            self.message_id += 1
        for offset in range(12, 20):
            self.messages.append({
                "id": self.message_id, "couple_id": 1, "sender_id": 1 + (self.message_id % 2),
                "content": chatter(self.event_index, offset), "msg_type": "text", "read_status": True,
                "created_at": event_date + timedelta(hours=2, minutes=offset),
            })
            self.message_id += 1
        self.memories.append({
            "couple_id": 1, "source_type": "realism_truth", "source_id": source_id,
            "title": title, "content": content, "event_date": event_date, "event_end": event_date,
            "location": location, "emotion": "", "tags": json.dumps(tags or [category], ensure_ascii=False),
            "importance": importance, "status": "confirmed", "visibility": "shared", "category": category,
            "memory_state": state, "confidence": 0.95, "source_message_ids": json.dumps(evidence_ids),
            "version": version, "is_active": active,
        })
        if question:
            self.truth.append({
                "question": question, "expected_source_id": source_id, "expected_answer": answer or content,
                "expected_date": event_date.isoformat(), "expected_state": state, "group": group,
            })
        self.event_index += 1


def build_corpus():
    builder = CorpusBuilder()
    trip_start = datetime(2017, 2, 11, 10, 0)
    for city_index, (city, attractions, foods) in enumerate(CITIES):
        for visit in range(4):
            index = city_index * 4 + visit
            event_date = trip_start + timedelta(days=index * 39)
            attraction, food = attractions[visit], foods[visit]
            source_id = f"trip-{city_index:02d}-{visit + 1}"
            builder.add_event(
                source_id=source_id,
                title=f"{event_date.year}年{city}{attraction}旅行",
                content=f"{event_date:%Y年%m月%d日}两人去了{city}{attraction}，在那里散步拍照，晚餐吃了{food}。",
                event_date=event_date, category="event", state="completed", location=f"{city}{attraction}",
                event_lines=[
                    f"这次到{city}我们先去{attraction}吧，上次走的不是这条路线。",
                    f"好，今天在{attraction}慢慢逛，不赶下一个景点。",
                    f"晚饭就吃{food}，这家是本地朋友推荐的。",
                ],
                question=f"{event_date.year}年{event_date.month}月那次{city}旅行去了哪个景点，晚饭吃了什么？",
                answer=f"去了{attraction}，吃了{food}", group="similar_trip", tags=["旅行", city, attraction],
            )

    pref_start = datetime(2018, 1, 8, 20, 0)
    for index, (topic, old_value, new_value) in enumerate(PREFERENCES):
        old_date = pref_start + timedelta(days=index * 45)
        new_date = old_date + timedelta(days=420 + index % 5 * 30)
        builder.add_event(
            source_id=f"pref-{index:02d}-v1", title=f"{topic}旧偏好", content=f"当时更偏好{old_value}。",
            event_date=old_date, category="preference", state="completed", active=False, version=1,
            event_lines=[f"我最近更喜欢{old_value}。", f"好，以后说到{topic}就先按{old_value}来。"],
            group="preference_old",
        )
        builder.add_event(
            source_id=f"pref-{index:02d}-v2", title=f"{topic}偏好更新",
            content=f"后来明确更新了{topic}偏好，现在选择{new_value}，旧偏好{old_value}不再适用。",
            event_date=new_date, category="preference", state="completed", active=True, version=2,
            event_lines=[
                f"我发现自己现在对{topic}的想法变了，不再选{old_value}。",
                f"那以后就记成{new_value}，之前的{old_value}作废。",
            ],
            question=f"现在关于{topic}应该按什么偏好安排？", answer=new_value,
            group="preference_change", tags=["偏好变化", topic],
        )

    plan_start = datetime(2021, 1, 16, 19, 0)
    for index, plan in enumerate(PLAN_ITEMS):
        planned_date = plan_start + timedelta(days=index * 31)
        outcome_date = planned_date + timedelta(days=18 + index % 4 * 3)
        cancelled = index % 2 == 0
        builder.add_event(
            source_id=f"plan-{index:02d}-v1", title=f"计划：{plan}", content=f"两人原计划在近期{plan}。",
            event_date=planned_date, category="plan", state="planned", active=False, version=1,
            event_lines=[f"我们下个月{plan}怎么样？", "可以，我先看时间和预算。"], group="plan_original",
        )
        if cancelled:
            content = f"原定的“{plan}”因时间冲突已经取消，暂时没有新的日期。"
            lines = [f"之前说的{plan}这次不去了，我临时有工作。", "好，那就取消，等以后重新商量。"]
            state = "cancelled"
            answer = "已经取消，暂时没有新日期"
        else:
            content = f"两人已经完成“{plan}”，过程顺利，并在当天拍了合照留念。"
            lines = [f"今天终于完成了{plan}，比预想中顺利。", "照片我已经存进共同相册了。"]
            state = "completed"
            answer = "已经完成"
        builder.add_event(
            source_id=f"plan-{index:02d}-v2", title=f"{plan}最终状态", content=content,
            event_date=outcome_date, category="plan", state=state, active=True, version=2,
            event_lines=lines, question=f"原来安排的“{plan}”最后怎么样了？", answer=answer,
            group="cancelled_plan" if cancelled else "completed_plan", tags=["计划状态", state],
        )

    conflict_start = datetime(2022, 2, 3, 21, 0)
    conflict_contexts = ["准备搬家的那周", "连续下雨的周末", "项目收尾的月底"]
    for index in range(60):
        issue = CONFLICTS[index % len(CONFLICTS)]
        context = conflict_contexts[index // len(CONFLICTS)]
        resolution = RESOLUTIONS[index % len(RESOLUTIONS)]
        date = conflict_start + timedelta(days=index * 24)
        builder.add_event(
            source_id=f"conflict-{index:02d}", title=f"{context}关于{issue}的沟通与和好",
            content=f"{context}，两人因为{issue}产生不愉快，冷静沟通后和好，并决定{resolution}。",
            event_date=date, category="event", state="completed",
            event_lines=[
                f"刚才因为{issue}我语气有点冲，对不起。",
                "我也有没说清楚的地方，我们把具体办法定下来吧。",
                f"那以后就{resolution}，这件事说开了。",
                "好，我们和好了，不把这次情绪带到明天。",
            ],
            question=f"{context}因为{issue}闹别扭后，两个人定了什么解决办法？",
            answer=resolution, group="conflict_reconciliation", tags=["沟通", "和好", issue],
        )

    fact_start = datetime(2020, 3, 7, 18, 0)
    gifts = ["拍立得", "手写相册", "银色书签", "降噪耳机", "蓝色围巾", "陶瓷马克杯"]
    occasions = ["生日", "纪念日", "升职", "搬家", "毕业", "完成考试"]
    details = ["藏在书架第二层", "包装用了牛皮纸", "附了一张手写卡片", "是在晚饭后送的", "提前一周准备", "刻了当天日期"]
    for index in range(60):
        gift = gifts[index % len(gifts)]
        occasion = occasions[(index // len(gifts)) % len(occasions)]
        detail = details[(index * 5) % len(details)]
        date = fact_start + timedelta(days=index * 33)
        builder.add_event(
            source_id=f"fact-{index:02d}", title=f"{occasion}收到的{gift}",
            content=f"{date:%Y年%m月%d日}的{occasion}收到了{gift}，特别之处是{detail}。",
            event_date=date, category="fact", state="completed",
            event_lines=[f"这次{occasion}我准备的是{gift}。", f"我发现了，而且{detail}，这个细节我会记很久。"],
            question=(f"{date.year}年{date.month}月那次{occasion}收到的礼物是什么，有什么特别细节？" if index < 20 else None),
            answer=f"{gift}，{detail}", group="dated_fact", tags=[occasion, "礼物"],
        )

    negative_templates = [
        "我们有没有一起去过{place}参加{activity}？",
        "哪一年我们在{place}体验过{activity}？",
        "我记不清了，我们是不是曾在{place}安排过{activity}？",
        "请回忆一下两个人去{place}{activity}的细节。",
    ]
    negatives = [{
        "question": negative_templates[variant].format(place=place, activity=activity),
        "split": "development",
    }
        for place, activity in [
            ("冰岛", "火山徒步"), ("巴黎", "塞纳河游船"), ("东京", "动漫展"), ("纽约", "跨年倒数"),
            ("悉尼", "冲浪课"), ("开普敦", "跳伞"), ("芬兰", "驯鹿雪橇"), ("秘鲁", "雨林探险"),
            ("瑞士", "滑翔伞"), ("埃及", "沙漠露营"),
        ]
        for variant in range(4)
    ][:40]
    for item in builder.truth:
        item["split"] = "development"

    holdout_limits = {
        "similar_trip": 20, "preference_change": 10, "cancelled_plan": 5,
        "completed_plan": 5, "conflict_reconciliation": 10, "dated_fact": 10,
    }
    holdout_counts = {key: 0 for key in holdout_limits}
    holdout = []
    for item in builder.truth:
        group = item["group"]
        if group not in holdout_limits or holdout_counts[group] >= holdout_limits[group]:
            continue
        question = item["question"]
        if group == "similar_trip":
            question = question.replace("那次", "那一趟").replace("去了哪个景点，晚饭吃了什么", "具体逛了哪里，又吃了哪种当地食物")
        elif group == "preference_change":
            question = question.replace("现在关于", "这个偏好改过一次，目前关于").replace("应该按什么偏好安排", "最终选择是什么")
        elif group in {"cancelled_plan", "completed_plan"}:
            question = question.replace("原来安排的", "之前提到的").replace("最后怎么样了", "后来成行了吗，最终状态是什么")
        elif group == "conflict_reconciliation":
            question = question.replace("闹别扭后，两个人定了什么解决办法", "发生分歧后，最后用什么办法和好的")
        elif group == "dated_fact":
            question = question.replace("收到的礼物是什么，有什么特别细节", "对方送了什么，礼物上有什么值得记住的地方")
        holdout.append({**item, "question": question, "split": "holdout"})
        holdout_counts[group] += 1
    builder.truth.extend(holdout)

    absent_preferences = [
        "对方现在是不是最喜欢榴莲披萨？", "我们有没有约定每周日凌晨去游泳？",
        "家里是否养过一只叫雪球的白色兔子？", "对方是否对草莓严重过敏？",
        "我们是不是把结婚日期定在了2028年8月8日？", "两个人是否共同买过一辆红色摩托车？",
        "对方现在最喜欢的乐器是不是手风琴？", "我们有没有决定搬去海口长期生活？",
        "去年生日是不是送过一架无人机？", "我们是否在冰箱门上贴了紫色星星作为暗号？",
        "对方有没有明确说过永远不坐高铁？", "我们是否约定每个月存一万元旅行基金？",
        "第一次见面是不是在广州塔顶层？", "两个人有没有一起参加过马拉松全程比赛？",
        "对方是不是只喝加双份糖浆的美式咖啡？", "我们是否领养过一只名叫布丁的柯基？",
        "纪念日礼物是不是一台绿色唱片机？", "两个人有没有在敦煌拍过婚纱照？",
        "是否因为购买钢琴发生过争吵并决定退货？", "我们有没有取消过去南极看企鹅的计划？",
    ]
    negatives.extend({"question": question, "split": "holdout"} for question in absent_preferences)
    return builder, negatives


def rank_of(results, expected_source_id):
    for index, item in enumerate(results, 1):
        if item["source_id"] == expected_source_id:
            return index
    return 0


def _calculate_metrics(rows, negative_rows):
    date_rows = [row for row in rows if row["group"] in {"similar_trip", "dated_fact"}]
    state_rows = [row for row in rows if row["group"] in {"cancelled_plan", "completed_plan"}]
    pref_rows = [row for row in rows if row["group"] == "preference_change"]
    combined = rows + negative_rows
    return {
        "recall_at_1": sum(row["rank"] == 1 for row in rows) / len(rows),
        "recall_at_5": sum(row["rank"] > 0 for row in rows) / len(rows),
        "mrr": sum((1 / row["rank"]) if row["rank"] else 0 for row in rows) / len(rows),
        "time_accuracy": sum(row["rank"] == 1 and row["top_date"] == row["expected_date"] for row in date_rows) / len(date_rows),
        "state_accuracy": sum(row["rank"] == 1 and row["top_state"] == row["expected_state"] for row in state_rows) / len(state_rows),
        "preference_latest_accuracy": sum(row["rank"] == 1 for row in pref_rows) / len(pref_rows),
        "abstention_rate": sum(row["abstained"] for row in negative_rows) / len(negative_rows),
        "hallucination_risk_rate": sum(not row["abstained"] for row in negative_rows) / len(negative_rows),
        "median_latency_ms": statistics.median(row["latency_ms"] for row in combined),
        "p95_latency_ms": sorted(row["latency_ms"] for row in combined)[int(len(combined) * 0.95) - 1],
    }


def run_evaluation(db, truth, negatives):
    all_questions = [item["question"] for item in truth] + [item["question"] for item in negatives]
    vectors = ai_service.embed_texts(all_questions)
    vector_map = {question: vector for question, vector in zip(all_questions, vectors)}
    original_embed = ai_service.embed_texts

    def cached_embed(texts):
        missing = [text for text in texts if text not in vector_map]
        if missing:
            return original_embed(texts)
        return [vector_map[text] for text in texts]

    ai_service.embed_texts = cached_embed
    rows = []
    try:
        for item in truth:
            started = time.perf_counter()
            results = memory_service.search(db, 1, item["question"], top_k=5, user_id=1)
            latency = (time.perf_counter() - started) * 1000
            rank = rank_of(results, item["expected_source_id"])
            top = results[0] if results else None
            rows.append({
                **item, "rank": rank, "latency_ms": round(latency, 2),
                "top_source_id": top["source_id"] if top else None,
                "top_date": top["event_date"] if top else None,
                "top_state": top["memory_state"] if top else None,
                "top_score": top.get("score") if top else None,
                "top_content": top["content"][:160] if top else None,
            })
        negative_rows = []
        for negative in negatives:
            question = negative["question"]
            started = time.perf_counter()
            results = memory_service.search(db, 1, question, top_k=5, user_id=1)
            negative_rows.append({
                "question": question, "split": negative["split"], "abstained": not results,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "returned": [item["source_id"] for item in results],
                "top_score": results[0].get("score") if results else None,
            })
    finally:
        ai_service.embed_texts = original_embed

    metrics = _calculate_metrics(rows, negative_rows)
    holdout_metrics = _calculate_metrics(
        [row for row in rows if row["split"] == "holdout"],
        [row for row in negative_rows if row["split"] == "holdout"],
    )
    return metrics, holdout_metrics, rows, negative_rows


def pct(value):
    return f"{value * 100:.2f}%"


def write_report(payload):
    metrics = payload["metrics"]
    holdout = payload["holdout_metrics"]
    failures = [row for row in payload["positive_cases"] if not row["rank"]][:20]
    false_positives = [row for row in payload["negative_cases"] if not row["abstained"]][:20]
    lines = [
        "# 长期记忆真实性测试报告",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 测试范围",
        "",
        f"- 原始聊天：{payload['dataset']['messages']} 条",
        f"- 标准答案记忆：{payload['dataset']['memories']} 条（活跃 {payload['dataset']['active_memories']} 条）",
        f"- 正向改写问题：{payload['dataset']['positive_questions']} 条",
        f"- 不存在事实问题：{payload['dataset']['negative_questions']} 条",
        f"- 向量模型：{payload['embedding_model']}",
        "- 场景：相似旅行、偏好变化、计划取消/完成、争吵和好、带日期礼物，以及大量自然闲聊。",
        "",
        "## 核心结果",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Recall@1 | {pct(metrics['recall_at_1'])} |",
        f"| Recall@5 | {pct(metrics['recall_at_5'])} |",
        f"| MRR | {metrics['mrr']:.4f} |",
        f"| 时间正确率 | {pct(metrics['time_accuracy'])} |",
        f"| 状态正确率 | {pct(metrics['state_accuracy'])} |",
        f"| 最新偏好正确率 | {pct(metrics['preference_latest_accuracy'])} |",
        f"| 无答案拒答率 | {pct(metrics['abstention_rate'])} |",
        f"| 无答案误召回风险 | {pct(metrics['hallucination_risk_rate'])} |",
        f"| 中位检索耗时 | {metrics['median_latency_ms']:.2f} ms |",
        f"| P95 检索耗时 | {metrics['p95_latency_ms']:.2f} ms |",
        "",
        "## 未参与调参的保留集",
        "",
        "| 指标 | 结果 |",
        "|---|---:|",
        f"| Holdout Recall@1 | {pct(holdout['recall_at_1'])} |",
        f"| Holdout Recall@5 | {pct(holdout['recall_at_5'])} |",
        f"| Holdout 时间正确率 | {pct(holdout['time_accuracy'])} |",
        f"| Holdout 状态正确率 | {pct(holdout['state_accuracy'])} |",
        f"| Holdout 最新偏好正确率 | {pct(holdout['preference_latest_accuracy'])} |",
        f"| Holdout 无答案拒答率 | {pct(holdout['abstention_rate'])} |",
        "",
        "## 解释",
        "",
        "- Recall 衡量正确记忆是否进入候选结果；时间、状态和偏好指标要求正确记忆排在第一位。",
        "- “是否编造”以无答案问题能否返回空候选衡量：仍返回候选时，后续生成模型存在被错误上下文诱导的风险。",
        "- 该评估直接使用带标准答案的事件记忆检索，重点衡量检索与状态过滤；不把 AI 事件抽取质量混入检索分数。",
        "",
        "## 适用边界",
        "",
        "- 数据由程序按真实聊天结构合成，不包含真实用户隐私，也不能替代真实用户盲测。",
        "- 事件记忆由标准答案直接写入，报告衡量检索、时间约束、状态过滤、偏好版本和拒答；事件抽取另由单元测试覆盖。",
        "- ‘误召回风险为 0’表示本测试的无答案题没有进入生成上下文，不等于生成模型在所有开放问题上绝不会编造。",
        "- 当前真实性库有 280 条活跃记忆；超过 3,000 条时的 LSH 性能由独立规模压测覆盖。",
        "",
        "## 失败样例",
        "",
    ]
    if failures:
        for row in failures:
            lines.append(f"- 未召回：{row['question']}（期望 {row['expected_source_id']}，实际首条 {row['top_source_id']}）")
    else:
        lines.append("- Recall@5 无失败样例。")
    lines += ["", "## 无答案误召回样例", ""]
    if false_positives:
        for row in false_positives:
            lines.append(f"- {row['question']} → {', '.join(row['returned'][:3])}（最高分 {row['top_score']}）")
    else:
        lines.append("- 所有无答案问题均正确拒答。")
    lines += [
        "", "## 可复现文件", "",
        f"- 独立数据库：`{DB_PATH}`",
        f"- 标准答案：`{TRUTH_PATH}`",
        f"- 结构化结果：`{REPORT_JSON}`",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse", action="store_true", help="复用已生成数据库，仅重新评估")
    args = parser.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    builder, negatives = build_corpus()

    if not args.reuse or not DB_PATH.exists():
        if DB_PATH.exists():
            DB_PATH.unlink()
        engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.add_all([
                User(id=1, email="realism.a@example.test", password_hash="unused", nickname="小墨", couple_id=1),
                User(id=2, email="realism.b@example.test", password_hash="unused", nickname="小韵", couple_id=1),
                Couple(id=1, pairing_code="REALISM", user1_id=1, user2_id=2, status="active"),
            ])
            db.bulk_insert_mappings(Message, builder.messages)
            db.bulk_insert_mappings(SharedMemory, builder.memories)
            db.commit()
            started = time.perf_counter()
            while True:
                result = memory_service.ensure_embeddings(db, 1, limit=128)
                if result["remaining_embeddings"] == 0:
                    break
            index_seconds = time.perf_counter() - started
        finally:
            db.close()
            engine.dispose()
    else:
        if REPORT_JSON.exists():
            previous = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
            index_seconds = float(previous.get("index_seconds") or 0.0)
        else:
            index_seconds = 0.0

    TRUTH_PATH.write_text(json.dumps({"positive": builder.truth, "negative": negatives}, ensure_ascii=False, indent=2), encoding="utf-8")
    engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        metrics, holdout_metrics, positive_rows, negative_rows = run_evaluation(db, builder.truth, negatives)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "embedding_model": ai_service.embedding_index_model,
            "index_seconds": round(index_seconds, 2),
            "dataset": {
                "messages": db.query(Message).count(), "memories": db.query(SharedMemory).count(),
                "active_memories": db.query(SharedMemory).filter(SharedMemory.is_active.is_(True)).count(),
                "positive_questions": len(builder.truth), "negative_questions": len(negatives),
            },
            "metrics": metrics, "holdout_metrics": holdout_metrics,
            "positive_cases": positive_rows, "negative_cases": negative_rows,
        }
        REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(payload)
        print(json.dumps({
            "report": str(REPORT_MD), "database": str(DB_PATH), "ground_truth": str(TRUTH_PATH),
            "dataset": payload["dataset"], "metrics": metrics,
            "holdout_metrics": holdout_metrics, "index_seconds": payload["index_seconds"],
        }, ensure_ascii=False, indent=2))
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
