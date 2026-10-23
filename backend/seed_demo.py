"""写入虚构的双人演示数据；可重复运行，不删除其他用户数据。"""
import argparse
import json
from datetime import date, datetime, time, timedelta
from html import escape
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings as app_settings
from app.database import Base, SessionLocal, init_db
from app.models import (
    Anniversary, Couple, CoupleAISettings, Diary, Message, Photo, Recipe,
    RecipeComment, RecipeRating, SharedMemory, User,
)
from app.services.memory_service import memory_service
from app.utils import hash_password


DEMO_EMAILS = ("demo.a@example.com", "demo.b@example.com")
DEMO_PASSWORD = "Demo123456!"
DEMO_START = date(2026, 4, 23)
DEMO_END = date(2026, 10, 23)

CHAT_SCENES = [
    ("早呀，今天记得吃早餐。", "吃啦，豆浆和鸡蛋，你也别空腹喝咖啡。", "收到，晚上一起散步二十分钟。"),
    ("今晚想吃什么？", "想吃{dish}，少辣一点。", "好，我下班顺路买菜，七点左右到家。"),
    ("今天工作有点多，脑袋快转不动了。", "辛苦啦，先喝口水，不急着马上回消息。", "看到这句好多了，回家想抱一下。"),
    ("周末去{place}怎么样？", "可以，上午人少，我们早点出发。", "那我来做路线，预算还是控制在三百以内。"),
    ("刚看到一只特别像小狐狸的狗狗。", "快发给我看！", "拍糊了，但已经收藏进今天的快乐了。"),
    ("你昨晚是不是没睡好？", "有一点，半夜醒了两次。", "今晚我们早点放下手机，我陪你听会儿音乐。"),
    ("冰箱里的牛奶快过期了。", "我晚上拿来做燕麦，水果也一起解决掉。", "好，避免浪费小分队再次出动。"),
    ("刚才语气有点急，对不起。", "没关系，我知道你是着急，不是在针对我。", "谢谢你愿意说开，晚上我们再慢慢聊。"),
    ("下个月想留一个完整周末出去走走。", "我也想，武汉和南京二选一？", "先看车票，决定好了就写进计划。"),
    ("今天的云特别好看。", "我也看到了，像我们在重庆拍到的那片晚霞。", "那次走得腿疼，但现在想起来全是开心。"),
    ("要不要开始存旅行基金？", "每个人每月五百，单独记账。", "成交，年底争取去看一次海。"),
    ("你上次推荐的歌我循环了一下午。", "哪一首？我再给你凑个通勤歌单。", "就那首慢慢的，听起来很安心。"),
    ("今天想偷懒不做饭。", "批准，点一份清淡的，我们一起选。", "那吃馄饨吧，吃完我洗碗。"),
    ("妈妈问我们最近怎么样。", "就说挺好的，周末有空一起打个视频。", "好，也提醒我把给叔叔阿姨的礼物寄出去。"),
    ("我把客厅收拾好了。", "太棒了，我负责卧室和倒垃圾。", "分工完成，今晚奖励一部电影。"),
    ("最近你最想实现的小愿望是什么？", "想和你拍一组自然一点的合照。", "记下了，等天气好我们去江边拍。"),
    ("中午吃了什么？", "同事一起去吃了{dish}，味道还不错。", "那我今晚换个口味，给你做番茄鸡蛋面。"),
    ("降温了，外套带了吗？", "带了，你放门口那件刚好。", "那就好，回来路上别骑太快。"),
    ("我们第一次旅行到底是武汉还是重庆？", "武汉是第一次，重庆是第二次，别又记反啦。", "这次记牢了：武汉先，重庆后。"),
    ("芒果到啦，闻起来很甜。", "给我留两个，别一次吃太多。", "遵命，给你挑最大的那个。"),
    ("这个月是不是超预算了一点？", "主要是旅行订票，日常开销还好。", "那下周多在家做饭，顺便研究新菜。"),
    ("突然想起我们第一次见面都不敢看对方。", "你还把咖啡糖包拆到桌上了。", "别揭短，明明是紧张得手忙脚乱。"),
    ("今天给自己打几分？", "六分，事情做完了但有点累。", "那剩下四分交给晚饭、热水澡和我。"),
    ("十一月想去南京看秋天。", "想去梧桐大道，也想吃鸭血粉丝汤。", "我来做攻略，你负责挑住的地方。"),
]

DIARY_SCENES = [
    ("雨天电影夜", "外面一直下雨，我们取消了出门计划，在家做意面、看老电影。原来普通的一天也能很温暖。", "温暖"),
    ("江边的晚风", "晚饭后沿着江边走了很久，聊工作，也聊年底想去看的海。风有点凉，但牵着手刚刚好。", "开心"),
    ("第一次一起做蛋糕", "奶油打过头，草莓也切得不整齐，成品却比买来的更有纪念意义。", "甜蜜"),
    ("说开以后", "因为行程安排闹了点别扭，好在没有冷战。把各自担心的事情说开之后，反而更理解彼此。", "释然"),
    ("周末逛展", "看了期待很久的摄影展，最喜欢那组关于城市夜晚的照片，出来后在安静的咖啡店坐到傍晚。", "满足"),
    ("武汉旅行回忆", "整理旧照片时又想起第一次一起去武汉。迷过路，也赶上过雨，但从黄鹤楼下来时我们笑得很开心。", "怀念"),
    ("家常饭最好吃", "今天没有特别安排，只一起买菜、洗菜、做番茄牛腩。厨房有点乱，饭桌上的聊天却很踏实。", "安心"),
    ("忙碌的一周", "这周两个人都很忙，回复消息变慢了，但每天都会认真说晚安。陪伴不一定要很热闹。", "平静"),
    ("重庆的夜景", "第二次旅行去了重庆，在洪崖洞看夜景。走了很多坡路，回酒店后互相贴膏药，想起来又好笑。", "开心"),
    ("旅行基金启动", "决定每人每月存五百元做旅行基金，希望年底能一起去看海。共同计划让未来变得具体起来。", "期待"),
    ("被记住的小事", "随口说了一句最近胃不舒服，晚饭就变成了清淡的粥。被认真放在心上的感觉很好。", "感动"),
    ("一起整理房间", "分工收拾了客厅和卧室，翻出第一次约会留下的电影票。舍不得扔，最后放进了纪念盒。", "幸福"),
    ("夏夜散步", "避开白天的热气，晚上绕小区走了三圈。我们约好每周至少运动两次，互相监督。", "轻松"),
    ("给未来的清单", "列下想一起完成的十件事：看海、露营、学一道拿手菜、拍自然的合照……慢慢完成就好。", "期待"),
    ("认真道歉", "今天听见了一句很真诚的对不起。比起谁输谁赢，我们更想知道以后怎样做得更好。", "释然"),
    ("秋天的第一杯热饮", "天气突然转凉，一起买了热饮走回家。开始期待梧桐变黄，也开始计划十一月的南京之行。", "甜蜜"),
]

PHOTO_TITLES = [
    "江边晚风", "周末早餐", "一起逛展", "雨后街道", "自制蛋糕", "公园野餐",
    "武汉旧照", "重庆夜景", "家常晚饭", "咖啡店窗边", "散步随拍", "旅行车票",
    "晚霞合影", "电影票根", "新买的花", "厨房合作", "猫咪偶遇", "秋日梧桐",
]

RECIPE_DATA = [
    ("番茄鸡蛋面", "鸡蛋", "dinner"), ("土豆炖牛腩", "牛腩", "dinner"),
    ("香煎鸡胸沙拉", "鸡胸肉", "lunch"), ("南瓜小米粥", "南瓜", "breakfast"),
    ("低辣麻婆豆腐", "嫩豆腐", "dinner"), ("可乐鸡翅", "鸡翅", "dinner"),
    ("虾仁滑蛋", "虾仁", "lunch"), ("芒果酸奶杯", "芒果", "dessert"),
    ("蒜香西兰花", "西兰花", "dinner"), ("黑椒牛肉意面", "牛肉", "dinner"),
    ("香蕉燕麦松饼", "香蕉", "breakfast"), ("红糖姜奶茶", "牛奶", "drink"),
    ("清蒸鲈鱼", "鲈鱼", "dinner"), ("番茄牛腩锅", "番茄", "dinner"),
    ("照烧鸡腿饭", "鸡腿", "lunch"), ("菌菇豆腐汤", "菌菇", "dinner"),
    ("空气炸锅薯角", "土豆", "snack"), ("草莓奶油蛋糕", "草莓", "dessert"),
    ("青椒肉丝", "猪里脊", "dinner"), ("葱油拌面", "面条", "lunch"),
    ("紫菜虾皮馄饨", "馄饨", "breakfast"), ("蜂蜜柠檬水", "柠檬", "drink"),
    ("咖喱鸡肉饭", "鸡腿肉", "dinner"), ("荷塘小炒", "莲藕", "dinner"),
    ("玉米排骨汤", "排骨", "dinner"), ("金枪鱼三明治", "全麦面包", "breakfast"),
    ("桂花酒酿圆子", "酒酿", "dessert"), ("孜然烤蘑菇", "口蘑", "snack"),
    ("肉末蒸蛋", "鸡蛋", "dinner"), ("鲜虾蔬菜粥", "鲜虾", "breakfast"),
    ("糖醋里脊", "猪里脊", "dinner"), ("抹茶红豆奶冻", "牛奶", "dessert"),
    ("酸汤肥牛", "肥牛", "dinner"), ("芝士火腿吐司", "吐司", "breakfast"),
    ("冰糖雪梨", "雪梨", "drink"), ("香菇鸡肉焖饭", "鸡腿肉", "lunch"),
]


def get_or_create_user(db, email: str, nickname: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, nickname=nickname, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
    return user


def add_once(db, model, filters: dict, values: dict):
    item = db.query(model).filter_by(**filters).first()
    if not item:
        item = model(**values)
        db.add(item)
        db.flush()
    return item


def seed_chat(db, couple: Couple, users: tuple[User, User]):
    dishes = ["番茄牛腩", "菌菇汤", "虾仁滑蛋", "鸡肉焖饭", "清蒸鱼", "馄饨"]
    places = ["江边散步", "看摄影展", "植物园", "旧书店", "郊外露营", "博物馆"]
    active_index = 0
    for offset in range((DEMO_END - DEMO_START).days + 1):
        if offset % 8 == 7:
            continue
        day = DEMO_START + timedelta(days=offset)
        scene = CHAT_SCENES[active_index % len(CHAT_SCENES)]
        variables = {"dish": dishes[(active_index // 3) % len(dishes)], "place": places[(active_index // 4) % len(places)]}
        sender_pattern = (0, 1, 0) if active_index % 2 == 0 else (1, 0, 1)
        hours = (8, 12, 20) if active_index % 3 else (9, 18, 21)
        for part, raw in enumerate(scene):
            created_at = datetime.combine(day, time(hours[part], 5 + (active_index * 7 + part * 11) % 50))
            content = raw.format(**variables)
            add_once(db, Message, {
                "couple_id": couple.id, "sender_id": users[sender_pattern[part]].id,
                "content": content, "created_at": created_at,
            }, {
                "couple_id": couple.id, "sender_id": users[sender_pattern[part]].id,
                "content": content, "msg_type": "text", "read_status": True, "created_at": created_at,
            })
        active_index += 1


def seed_diaries(db, couple: Couple, users: tuple[User, User]):
    for index, offset in enumerate(range(2, (DEMO_END - DEMO_START).days + 1, 4)):
        day = DEMO_START + timedelta(days=offset)
        title, content, mood = DIARY_SCENES[index % len(DIARY_SCENES)]
        dated_title = f"{day.month}月{day.day}日 · {title}"
        created_at = datetime.combine(day, time(22, 10))
        add_once(db, Diary, {"couple_id": couple.id, "title": dated_title}, {
            "couple_id": couple.id, "author_id": users[index % 2].id, "title": dated_title,
            "content": content, "mood": mood, "created_at": created_at, "updated_at": created_at,
        })


def write_photo_svg(path: Path, title: str, day: date, index: int):
    colors = [("#f6d3d6", "#d36b72"), ("#cfe7e2", "#4d8b82"), ("#f8dfb8", "#d98d48"),
              ("#d9d2ee", "#7566a8"), ("#cfe0f5", "#5684bd"), ("#ead8c8", "#9f7655")]
    start, end = colors[index % len(colors)]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/></linearGradient></defs>
<rect width="1200" height="900" fill="url(#g)"/><circle cx="960" cy="180" r="90" fill="#fff" opacity=".45"/>
<path d="M0 690 Q260 500 520 690 T1200 610 V900 H0Z" fill="#fff" opacity=".26"/>
<text x="70" y="720" fill="#fff" font-size="58" font-family="Microsoft YaHei, sans-serif" font-weight="700">{escape(title)}</text>
<text x="74" y="785" fill="#fff" font-size="30" font-family="Microsoft YaHei, sans-serif" opacity=".9">{day.isoformat()} · 小墨和小韵</text>
</svg>'''
    if not path.exists():
        path.write_text(svg, encoding="utf-8")


def seed_album(db, couple: Couple, users: tuple[User, User]):
    app_settings.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    for index, offset in enumerate(range(1, (DEMO_END - DEMO_START).days + 1, 3)):
        day = DEMO_START + timedelta(days=offset)
        title = PHOTO_TITLES[index % len(PHOTO_TITLES)]
        stored_name = f"demo-six-month-{index + 1:03d}.svg"
        file_path = f"/uploads/photos/{stored_name}"
        write_photo_svg(app_settings.PHOTOS_DIR / stored_name, title, day, index)
        add_once(db, Photo, {"couple_id": couple.id, "file_path": file_path}, {
            "couple_id": couple.id, "uploader_id": users[index % 2].id, "filename": f"{title}.svg",
            "file_path": file_path, "created_at": datetime.combine(day, time(16, 20)),
        })


def seed_anniversaries(db, couple: Couple):
    events = [
        ("第一次见面", "在咖啡店第一次见面，两个人都紧张得不敢对视。", date(2026, 4, 26)),
        ("确定关系纪念日", "一起认真庆祝属于我们的这一天。", date(2026, 5, 20)),
        ("第一次合照", "在江边留下的第一张正式合照。", date(2026, 6, 2)),
        ("第一次旅行·武汉", "第一次一起坐高铁旅行，目的地是武汉。", date(2026, 6, 15)),
        ("小墨生日", "提前订蛋糕，准备一份不张扬但用心的礼物。", date(2026, 7, 12)),
        ("一起看海", "第一次在海边看日落。", date(2026, 8, 9)),
        ("搬家纪念日", "把两个人的东西慢慢整理成一个家。", date(2026, 9, 1)),
        ("第二次旅行·重庆", "记得洪崖洞的夜景和走不完的坡路。", date(2026, 10, 3)),
        ("小韵生日", "想吃草莓蛋糕，也想收到一封手写信。", date(2026, 11, 8)),
        ("年度回忆日", "一起整理照片和年度共同回忆。", date(2026, 12, 31)),
    ]
    for title, description, event_date in events:
        add_once(db, Anniversary, {"couple_id": couple.id, "title": title}, {
            "couple_id": couple.id, "title": title, "description": description, "date": event_date,
            "reminder_enabled": True, "created_at": datetime.combine(max(event_date, DEMO_START), time(10)),
        })


def seed_recipes(db, couple: Couple, users: tuple[User, User]):
    for index, (title, main_ingredient, category) in enumerate(RECIPE_DATA):
        created_day = DEMO_START + timedelta(days=3 + index * 5)
        recipe = add_once(db, Recipe, {"couple_id": couple.id, "title": title}, {
            "couple_id": couple.id, "author_id": users[index % 2].id, "chef_id": users[(index + 1) % 2].id,
            "title": title, "cover": f"/uploads/photos/demo-six-month-{index % 61 + 1:03d}.svg",
            "category": category, "difficulty": "medium" if index % 5 == 0 else "easy",
            "cook_time": 15 + (index % 6) * 10,
            "ingredients": json.dumps([
                {"name": main_ingredient, "amount": "2人份"}, {"name": "葱姜蒜", "amount": "适量"},
                {"name": "盐和生抽", "amount": "少量"}], ensure_ascii=False),
            "steps": json.dumps([
                f"将{main_ingredient}清洗并处理成适合入口的大小。",
                "准备配料，少油少盐调味，按食材熟成顺序烹饪。",
                "出锅前试味，两人一起装盘并记录下次改进。"], ensure_ascii=False),
            "cook_count": 1 + index % 8, "want_eat": index % 7 == 0,
            "created_at": datetime.combine(created_day, time(19, 30)),
            "updated_at": datetime.combine(created_day, time(20)),
        })
        for user_index, score in ((0, 4 + index % 2), (1, 5 if index % 3 else 4)):
            add_once(db, RecipeRating, {"recipe_id": recipe.id, "user_id": users[user_index].id}, {
                "recipe_id": recipe.id, "user_id": users[user_index].id, "score": score,
                "created_at": datetime.combine(created_day, time(20, 20 + user_index)),
            })
        comments = ["这道可以加入常做清单，下次再多一点配菜。", "味道很适合我们，周末还想再吃一次。"]
        add_once(db, RecipeComment, {
            "recipe_id": recipe.id, "user_id": users[index % 2].id, "content": comments[index % 2],
        }, {
            "recipe_id": recipe.id, "user_id": users[index % 2].id, "content": comments[index % 2],
            "created_at": datetime.combine(created_day, time(20, 40)),
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", help="可选的 SQLite 文件路径；省略时使用本地业务数据库")
    args = parser.parse_args()
    custom_engine = None
    if args.database:
        path = Path(args.database).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        custom_engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(custom_engine)
        db = sessionmaker(bind=custom_engine)()
    else:
        init_db()
        db = SessionLocal()
    try:
        user_a = get_or_create_user(db, DEMO_EMAILS[0], "小墨")
        user_b = get_or_create_user(db, DEMO_EMAILS[1], "小韵")
        users = (user_a, user_b)
        couple = db.query(Couple).filter(Couple.pairing_code == "LOVE2026").first()
        if not couple:
            couple = Couple(pairing_code="LOVE2026", user1_id=user_a.id, user2_id=user_b.id,
                            status="active", created_at=datetime.combine(date(2025, 5, 20), time(12)))
            db.add(couple)
            db.flush()
        couple.user1_id, couple.user2_id, couple.status = user_a.id, user_b.id, "active"
        user_a.couple_id = user_b.couple_id = couple.id

        seed_chat(db, couple, users)
        seed_diaries(db, couple, users)
        seed_album(db, couple, users)
        seed_anniversaries(db, couple)
        seed_recipes(db, couple, users)

        ai_settings = db.query(CoupleAISettings).filter(CoupleAISettings.couple_id == couple.id).first()
        if not ai_settings:
            ai_settings = CoupleAISettings(couple_id=couple.id)
            db.add(ai_settings)
        ai_settings.enabled = True
        ai_settings.include_chat = ai_settings.include_diary = True
        ai_settings.include_album = ai_settings.include_anniversary = True
        db.commit()

        memory_service.sync_sources(db, couple.id)
        private_facts = [
            (user_a, "我的饮食偏好", "最近胃不太舒服，约会吃饭尽量少辣。"),
            (user_b, "我的约会偏好", "我喜欢安静、有自然光的空间，不喜欢排队太久。"),
        ]
        for owner, title, content in private_facts:
            exists = db.query(SharedMemory).filter(
                SharedMemory.couple_id == couple.id, SharedMemory.owner_id == owner.id,
                SharedMemory.visibility == "private", SharedMemory.title == title,
                SharedMemory.content == content, SharedMemory.is_active.is_(True),
            ).first()
            if not exists:
                memory_service.create_manual(db, couple.id, owner.id, title, content, "private", "preference")

        counts = {
            "messages": db.query(Message).filter(Message.couple_id == couple.id).count(),
            "diaries": db.query(Diary).filter(Diary.couple_id == couple.id).count(),
            "photos": db.query(Photo).filter(Photo.couple_id == couple.id).count(),
            "anniversaries": db.query(Anniversary).filter(Anniversary.couple_id == couple.id).count(),
            "recipes": db.query(Recipe).filter(Recipe.couple_id == couple.id).count(),
            "memories": db.query(SharedMemory).filter(SharedMemory.couple_id == couple.id).count(),
        }
        print("Demo data is ready.")
        print(f"Timeline: {DEMO_START.isoformat()} to {DEMO_END.isoformat()}")
        print(f"Account A: {DEMO_EMAILS[0]}")
        print(f"Account B: {DEMO_EMAILS[1]}")
        print(f"Password: {DEMO_PASSWORD}")
        print(f"Pairing code: {couple.pairing_code}")
        print("Counts: " + json.dumps(counts, ensure_ascii=True))
    finally:
        db.close()
        if custom_engine is not None:
            custom_engine.dispose()


if __name__ == "__main__":
    main()
