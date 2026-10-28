import unittest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Couple, Message, User
from app.routers.chat import _message_timestamp, chat_calendar, chat_history


class ChatTimezoneTest(unittest.TestCase):
    def test_utc_output(self):
        stamp = _message_timestamp(datetime(2026, 10, 23, 5, 56))
        local = datetime.fromisoformat(stamp).astimezone(timezone(timedelta(hours=8)))
        self.assertEqual(local.hour, 13)
        self.assertEqual(local.minute, 56)
        self.assertEqual(_message_timestamp(local), stamp)

    def test_local_date_boundary_and_pagination(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                user = User(email='timezone@example.com', password_hash='unused')
                db.add(user)
                db.flush()
                couple = Couple(pairing_code='timezone', user1_id=user.id, status='active')
                db.add(couple)
                db.flush()
                for hour in (15, 16):
                    db.add(Message(couple_id=couple.id, sender_id=user.id, content=str(hour), created_at=datetime(2026, 10, 23, hour)))
                db.commit()
                # 北京时间 24 日零点 = UTC 23 日 16 点。
                rows = chat_history(limit=100, offset=0, before=datetime.fromisoformat('2026-10-24T00:00:00+08:00'), user=user, couple=couple, db=db)
                self.assertEqual([row['content'] for row in rows], ['15'])
                older = chat_history(limit=100, offset=0, before=datetime.fromisoformat(rows[0]['created_at']), user=user, couple=couple, db=db)
                self.assertEqual(older, [])

                calendar = chat_calendar(timezone_offset=480, user=user, couple=couple, db=db)
                self.assertEqual(calendar['first_date'], '2026-10-23')
                self.assertEqual(calendar['last_date'], '2026-10-24')
                self.assertEqual(calendar['days'], [
                    {'date': '2026-10-23', 'count': 1},
                    {'date': '2026-10-24', 'count': 1},
                ])
        finally:
            engine.dispose()
