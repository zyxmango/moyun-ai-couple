"""为演示情侣生成可重复、可清理的大规模聊天压测数据。"""
import argparse
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import engine, SessionLocal
from app.models import Message, User


BATCH_NAME = "demo-chat-80000-v1"
START_LOCAL = datetime(2018, 1, 1, 7, 30)
END_LOCAL = datetime(2026, 10, 23, 22, 30)

NOISE = (
    "早上好，今天也要加油。",
    "我已经到公司了。",
    "午饭吃了家常菜。",
    "下班路上注意安全。",
    "收到，我晚一点回复你。",
    "天气有点凉，多穿一件。",
    "我到家了。",
    "好的，知道啦。",
    "今天工作结束了。",
    "早点休息，晚安。",
)

EVENTS = (
    "这次旅行我们去了武汉东湖，坐在湖边聊了很久。",
    "今天约会去了南京博物院，最喜欢那件青瓷展品。",
    "以后一起去青岛看海，住宿预算控制在六百元以内。",
    "我喜欢清淡口味，不喜欢香菜，点菜时帮我备注一下。",
    "生日那天收到你送的手写相册，我特别开心。",
    "我们吵架后把话说开了，约定有情绪时先冷静十分钟。",
    "第一次一起做番茄牛腩很成功，这道菜以后可以常做。",
    "已经订好去重庆的票和酒店，记得带舒服的鞋。",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=80_000)
    return parser.parse_args()


def active_days():
    days = []
    current = START_LOCAL.replace(hour=0, minute=0)
    end = END_LOCAL.replace(hour=0, minute=0)
    index = 0
    while current <= end:
        # 每周保留两天没有聊天，用于验证日历灰显。
        if index % 7 not in (2, 6):
            days.append(current)
        current += timedelta(days=1)
        index += 1
    return days


def main():
    count = parse_args().count
    if count <= 0:
        raise SystemExit("count must be positive")

    db = SessionLocal()
    try:
        first = db.query(User).filter(User.email == "demo.a@example.com").first()
        second = db.query(User).filter(User.email == "demo.b@example.com").first()
        if not first or not second or not first.couple_id or first.couple_id != second.couple_id:
            raise SystemExit("demo couple is unavailable; run seed_demo.py first")
        couple_id = first.couple_id
        sender_ids = (first.id, second.id)
    finally:
        db.close()

    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS load_test_runs (
                name VARCHAR(100) PRIMARY KEY,
                couple_id INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                first_message_id INTEGER,
                last_message_id INTEGER,
                created_at DATETIME NOT NULL
            )
        """))
        existing = connection.execute(
            text("SELECT message_count, first_message_id, last_message_id FROM load_test_runs WHERE name=:name"),
            {"name": BATCH_NAME},
        ).first()
        if existing:
            print({"status": "already_loaded", "count": existing[0], "first_id": existing[1], "last_id": existing[2]})
            return

    days = active_days()
    first_id = None
    inserted = 0
    chunk_size = 2_000
    for chunk_start in range(0, count, chunk_size):
        rows = []
        for index in range(chunk_start, min(count, chunk_start + chunk_size)):
            day = days[index * len(days) // count]
            minute = 7 * 60 + (index * 47) % (15 * 60)
            local_time = day + timedelta(minutes=minute)
            created_at = local_time - timedelta(hours=8)
            if index == 42_420:
                content = "2023年5月18日我们在青岛栈桥捡到一枚蓝色贝壳，装进透明盒子，约定暗号是海风七号。"
            elif index % 397 == 0:
                content = EVENTS[(index // 397) % len(EVENTS)]
            else:
                content = NOISE[index % len(NOISE)]
            rows.append({
                "couple_id": couple_id,
                "sender_id": sender_ids[index % 2],
                "content": content,
                "msg_type": "text",
                "read_status": True,
                "created_at": created_at,
            })
        with engine.begin() as connection:
            connection.execute(Message.__table__.insert(), rows)
            if first_id is None:
                first_id = connection.execute(text("SELECT last_insert_rowid() - :offset"), {"offset": len(rows) - 1}).scalar_one()
        inserted += len(rows)
        print(f"inserted {inserted}/{count}")

    with engine.begin() as connection:
        last_id = connection.execute(text("SELECT MAX(id) FROM messages WHERE couple_id=:couple_id"), {"couple_id": couple_id}).scalar_one()
        connection.execute(text("""
            INSERT INTO load_test_runs(name, couple_id, message_count, first_message_id, last_message_id, created_at)
            VALUES (:name, :couple_id, :count, :first_id, :last_id, :created_at)
        """), {
            "name": BATCH_NAME,
            "couple_id": couple_id,
            "count": count,
            "first_id": first_id,
            "last_id": last_id,
            "created_at": datetime.utcnow(),
        })
    print({"status": "loaded", "count": count, "first_id": first_id, "last_id": last_id})


if __name__ == "__main__":
    main()
