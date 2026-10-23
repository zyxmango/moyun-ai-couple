import unittest
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, VerificationCode
from app.utils import hash_password


class PasswordFlowTest(unittest.TestCase):
    def test_registration_reset_and_legacy_email(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)

        def override_db():
            with sessions() as db:
                yield db

        def code(email, value, purpose='general', expired=False):
            with sessions() as db:
                db.add(VerificationCode(email=email, code=value, purpose=purpose, expires_at=datetime.utcnow() + timedelta(minutes=-1 if expired else 5)))
                db.commit()

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        try:
            email = 'password@example.com'
            code(email, '123456')
            payload = {'email': ' Password@Example.com ', 'code': '123456', 'password': 'initial-pass', 'nickname': '测试'}
            self.assertEqual(client.post('/api/auth/register', json=payload).status_code, 200)
            login = {'email': email, 'password': 'initial-pass'}
            self.assertEqual(client.post('/api/auth/login', json=login).status_code, 200)
            reset = {'email': email, 'code': '111111', 'password': 'updated-pass'}
            code(email, '111111')
            self.assertEqual(client.post('/api/auth/reset-password', json=reset).status_code, 400)
            code(email, '222222', 'reset_password', expired=True)
            self.assertEqual(client.post('/api/auth/reset-password', json={**reset, 'code': '222222'}).status_code, 400)
            code(email, '333333', 'reset_password')
            reset['code'] = '333333'
            self.assertEqual(client.post('/api/auth/reset-password', json={**reset, 'password': 'short'}).status_code, 422)
            self.assertEqual(client.post('/api/auth/reset-password', json=reset).status_code, 200)
            self.assertEqual(client.post('/api/auth/reset-password', json=reset).status_code, 400)
            self.assertEqual(client.post('/api/auth/login', json=login).status_code, 401)
            self.assertEqual(client.post('/api/auth/login', json={**login, 'password': 'updated-pass'}).status_code, 200)
            with sessions() as db:
                db.add(User(email=' Legacy@Example.com ', nickname='旧账号', password_hash=hash_password('legacy-pass')))
                db.commit()
            self.assertEqual(client.post('/api/auth/login', json={'email': 'legacy@example.com', 'password': 'legacy-pass'}).status_code, 200)
            code('legacy@example.com', '444444')
            self.assertEqual(client.post('/api/auth/login-code', json={'email': 'legacy@example.com', 'code': '444444'}).status_code, 200)
            self.assertEqual(client.post('/api/auth/login-code', json={'email': 'legacy@example.com', 'code': '444444'}).status_code, 400)
            self.assertEqual(client.post('/api/auth/register', json={**payload, 'email': 'legacy@example.com', 'code': '111111'}).status_code, 400)
        finally:
            app.dependency_overrides.clear()
            client.close()
            engine.dispose()
