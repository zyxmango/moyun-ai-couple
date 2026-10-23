import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Couple, User
from app.utils import create_access_token


class RelationshipDateTest(unittest.TestCase):
    def test_shared_date_validation_and_access(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)
        with session() as db:
            users = [User(email=f'date{i}@example.com', password_hash='unused') for i in range(3)]
            db.add_all(users)
            db.flush()
            couple = Couple(pairing_code='date-test', user1_id=users[0].id, user2_id=users[1].id, status='active')
            db.add(couple)
            db.flush()
            for user in users[:2]:
                user.couple_id = couple.id
            headers = [{'Authorization': f'Bearer {create_access_token(user.id)}'} for user in users]
            db.commit()

        def override_db():
            with session() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            url = '/api/couple/relationship-date'
            self.assertIsNone(client.get('/api/couple/info', headers=headers[0]).json()['relationship_start_date'])
            start = (date.today() - timedelta(days=180)).isoformat()
            self.assertEqual(client.put(url, headers=headers[0], json={'relationship_start_date': start}).status_code, 200)
            self.assertEqual(client.get('/api/couple/info', headers=headers[1]).json()['relationship_start_date'], start)
            self.assertEqual(client.put(url, headers=headers[0], json={'relationship_start_date': (date.today() + timedelta(days=1)).isoformat()}).status_code, 400)
            self.assertEqual(client.put(url, headers=headers[0], json={'relationship_start_date': 'invalid'}).status_code, 422)
            self.assertEqual(client.put(url, headers=headers[2], json={'relationship_start_date': start}).status_code, 403)
            self.assertEqual(client.get('/api/couple/info', headers=headers[1]).json()['relationship_start_date'], start)
        finally:
            app.dependency_overrides.clear()
            client.close()
            engine.dispose()
