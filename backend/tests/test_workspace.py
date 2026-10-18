"""Account isolation, durable jobs, provenance, and collaborative review integration tests."""
import io
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.auth import router as auth_router
from app.api.routes.analysis import router as analysis_router
from app.core.config import settings
from app.db.database import Base, get_db
from app.db.models import AnalysisJob, AuthSession, Membership, PasswordReset
from app.services.jobs import run_once, claim
from app.services.analysis_service import AnalysisService

SAMPLE = Path(__file__).resolve().parents[2] / 'client_data.xlsx'

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + str(Path(self.temp.name) / 'test.db'), connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.storage = patch.object(settings, 'ANALYSIS_WORKSPACE_PATH', Path(self.temp.name) / 'artifacts')
        self.storage.start()
        self.app = FastAPI()
        self.app.include_router(auth_router, prefix='/api')
        self.app.include_router(analysis_router, prefix='/api')
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.owner = self.register('owner@example.com')

    def tearDown(self):
        self.owner.close()
        self.storage.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def register(self, email, invite=''):
        client = TestClient(self.app)
        response = client.post('/api/auth/register', json={'email': email, 'password': 'long-secure-test-passphrase', 'full_name': email.split('@')[0], 'organization': 'Test organization', 'invite_token': invite})
        self.assertEqual(response.status_code, 201, response.text)
        client.headers['x-csrf-token'] = response.json()['csrf_token']
        return client

    def upload(self, client=None, filename='sample.xlsx'):
        response = (client or self.owner).post('/api/analysis/upload', files={'file': (filename, SAMPLE.read_bytes())})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()['analysis_id']

    def finish(self, aid):
        self.assertTrue(run_once(self.sessions))
        response = self.owner.get(f'/api/analysis/{aid}')
        self.assertEqual(response.json()['job']['state'], 'completed', response.text)

    def test_upload_preview_does_not_queue_and_binds_confirmed_file(self):
        files = {'file': ('sample.xlsx', SAMPLE.read_bytes())}
        anonymous = TestClient(self.app)
        self.assertEqual(anonymous.post('/api/analysis/preview', files=files).status_code, 401)
        result = self.owner.post('/api/analysis/preview', files=files)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()['valid'])
        self.assertEqual(self.owner.get('/api/analysis').json()['total'], 0)
        rejected = self.owner.post('/api/analysis/upload', files=files, data={'preview_hash': 'wrong'})
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(self.owner.get('/api/analysis').json()['total'], 0)
        accepted = self.owner.post('/api/analysis/upload', files=files, data={'preview_hash': result.json()['file_hash']})
        self.assertEqual(accepted.status_code, 202, accepted.text)
        with self.sessions() as db:
            member = db.get(Membership, 1)
            member.role = 'reviewer'
            db.commit()
        self.assertEqual(self.owner.post('/api/analysis/preview', files=files).status_code, 403)

    def test_auth_csrf_logout_and_expiry(self):
        anonymous = TestClient(self.app)
        self.assertEqual(anonymous.get('/api/analysis').status_code, 401)
        with self.sessions() as db:
            session = db.query(AuthSession).first()
            self.assertNotIn(session.token_hash, self.owner.cookies.values())
        csrf = self.owner.headers.pop('x-csrf-token')
        self.assertEqual(self.owner.post('/api/auth/logout').status_code, 403)
        self.owner.headers['x-csrf-token'] = csrf
        self.assertEqual(self.owner.post('/api/auth/logout', headers={'Origin':'https://evil.example'}).status_code, 403)
        self.assertEqual(self.owner.post('/api/auth/logout').status_code, 200)
        self.assertEqual(self.owner.get('/api/auth/me').status_code, 401)
        result = self.owner.post('/api/auth/login', json={'email':'owner@example.com','password':'long-secure-test-passphrase'})
        self.assertEqual(result.status_code, 200)
        with self.sessions() as db:
            db.query(AuthSession).update({'expires_at':datetime.now(UTC).replace(tzinfo=None)-timedelta(seconds=1)})
            db.commit()
        self.assertEqual(self.owner.get('/api/auth/me').status_code, 401)

    def test_password_reset_email_token_expiry_and_session_revocation(self):
        anonymous = TestClient(self.app)
        sent = []
        with patch.object(settings, 'SMTP_HOST', ''):
            self.assertEqual(anonymous.post('/api/auth/forgot-password', json={'email':'owner@example.com'}).status_code, 503)
        with patch.object(settings, 'SMTP_HOST', 'smtp.test'), patch.object(settings, 'SMTP_FROM_EMAIL', 'no-reply@example.com'), patch.object(settings, 'SMTP_PASSWORD', 'test-only'), patch('app.api.routes.auth.send_password_reset', side_effect=lambda email, url: sent.append((email, url))):
            self.assertEqual(anonymous.post('/api/auth/forgot-password', json={'email':'unknown@example.com'}).status_code, 202)
            self.assertEqual(sent, [])
            self.assertEqual(anonymous.post('/api/auth/forgot-password', json={'email':'owner@example.com'}).status_code, 202)
        self.assertEqual(sent[0][0], 'owner@example.com')
        from urllib.parse import parse_qs, urlparse
        token = parse_qs(urlparse(sent[0][1]).query)['token'][0]
        with self.sessions() as db:
            self.assertNotIn(token, db.query(PasswordReset).first().token_hash)
            db.query(PasswordReset).update({'expires_at':datetime.now(UTC).replace(tzinfo=None)-timedelta(seconds=1)})
            db.commit()
        self.assertEqual(anonymous.post('/api/auth/reset-password', json={'token':token, 'password':'new-long-secure-passphrase'}).status_code, 400)
        with self.sessions() as db:
            db.query(PasswordReset).update({'expires_at':datetime.now(UTC).replace(tzinfo=None)+timedelta(minutes=30)})
            db.commit()
        self.assertEqual(anonymous.post('/api/auth/reset-password', json={'token':token, 'password':'new-long-secure-passphrase'}).status_code, 200)
        self.assertEqual(self.owner.get('/api/auth/me').status_code, 401)
        self.assertEqual(anonymous.post('/api/auth/reset-password', json={'token':token, 'password':'another-long-passphrase'}).status_code, 400)
        self.assertEqual(anonymous.post('/api/auth/login', json={'email':'owner@example.com', 'password':'long-secure-test-passphrase'}).status_code, 401)
        self.assertEqual(anonymous.post('/api/auth/login', json={'email':'owner@example.com', 'password':'new-long-secure-passphrase'}).status_code, 200)

    def test_password_change_requires_current_password_and_revokes_sessions(self):
        self.assertEqual(self.owner.post('/api/auth/change-password', json={'current_password':'wrong','new_password':'new-long-secure-passphrase'}).status_code, 400)
        self.assertEqual(self.owner.post('/api/auth/change-password', json={'current_password':'long-secure-test-passphrase','new_password':'new-long-secure-passphrase'}).status_code, 200)
        self.assertEqual(self.owner.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.owner.post('/api/auth/login', json={'email':'owner@example.com','password':'new-long-secure-passphrase'}).status_code, 200)

    def test_organization_isolation_on_all_views_and_downloads(self):
        aid = self.upload()
        outsider = self.register('outsider@example.com')
        for suffix in ['', '/analysis','/rules','/ml','/xai','/report','/trail','/findings','/finding?key=x','/preprocessed.csv','/audit-report.pdf']:
            self.assertEqual(outsider.get(f'/api/analysis/{aid}{suffix}').status_code,404,suffix)
        for action in ['retry','cancel']:
            self.assertEqual(outsider.post(f'/api/analysis/{aid}/{action}').status_code,404)
        self.assertEqual(outsider.get('/api/analysis').json()['total'],0)
        outsider.close()

    def test_invites_roles_and_one_time_use(self):
        invitation = self.owner.post('/api/auth/invitations',json={'email':'reviewer@example.com','role':'reviewer'})
        token = invitation.json()['token']
        reviewer = self.register('reviewer@example.com',token)
        self.assertEqual(reviewer.get('/api/auth/me').json()['user']['role'],'reviewer')
        self.assertEqual(reviewer.post('/api/analysis/upload',files={'file':('sample.xlsx',SAMPLE.read_bytes())}).status_code,403)
        self.assertEqual(reviewer.post('/api/auth/invitations',json={'email':'another@example.com'}).status_code,403)
        anonymous=TestClient(self.app)
        response=anonymous.post('/api/auth/register',json={'email':'reviewer@example.com','password':'long-secure-test-passphrase','full_name':'Again','invite_token':token})
        self.assertEqual(response.status_code,400)
        reviewer.close()

    def test_upload_limits_safe_names_and_invalid_content(self):
        aid=self.upload(filename='../../unsafe.xlsx')
        with self.sessions() as db:
            from app.db.models import Analysis
            analysis=db.get(Analysis,aid)
            self.assertEqual(analysis.filename,'unsafe.xlsx')
            self.assertTrue(Path(analysis.file_path).is_relative_to(Path(self.temp.name)))
            self.assertNotIn('unsafe',Path(analysis.file_path).name)
        self.assertEqual(self.owner.post('/api/analysis/upload',files={'file':('fake.xlsx',b'not-excel')}).status_code,400)
        with patch.object(settings,'MAX_UPLOAD_SIZE',10):
            self.assertEqual(self.owner.post('/api/analysis/upload',files={'file':('sample.xlsx',SAMPLE.read_bytes())}).status_code,413)

    def test_queue_cancel_retry_and_interrupted_lease(self):
        aid=self.upload()
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}/report').status_code,409)
        self.assertEqual(self.owner.post(f'/api/analysis/{aid}/cancel').status_code,200)
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}').json()['job']['state'],'cancelled')
        self.assertEqual(self.owner.post(f'/api/analysis/{aid}/retry').status_code,200)
        with self.sessions() as db:
            first=claim(db)
            self.assertEqual(first[0],aid)
            self.assertIsNone(claim(db))
            job=db.get(AnalysisJob,aid)
            job.lease_until=datetime.now(UTC).replace(tzinfo=None)-timedelta(seconds=1)
            db.commit()
        self.finish(aid)
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}').json()['job']['attempts'],2)
        self.assertEqual(self.owner.post(f'/api/analysis/{aid}/retry').status_code,409)

    def test_failed_worker_can_retry(self):
        aid=self.upload()
        with patch.object(AnalysisService,'process_analysis',side_effect=ValueError('private internals')):
            self.assertTrue(run_once(self.sessions))
        response=self.owner.get(f'/api/analysis/{aid}').json()
        self.assertEqual(response['job']['state'],'failed')
        self.assertNotIn('private internals',response['job']['error'])
        self.assertEqual(self.owner.post(f'/api/analysis/{aid}/retry').status_code,200)
        self.finish(aid)

    def test_evidence_reviews_conflicts_and_approval_roles(self):
        aid=self.upload();self.finish(aid)
        findings=self.owner.get(f'/api/analysis/{aid}/findings').json()['items']
        key=next(f['key'] for f in findings if f['result']=='fail')
        detail=self.owner.get(f'/api/analysis/{aid}/finding',params={'key':key}).json()
        self.assertTrue(detail['source_cells'])
        self.assertTrue(all(c['cell'] and c['sheet']=='Data Sheet' for c in detail['source_cells']))
        self.assertIn('Formula',detail['evidence'])
        token=self.owner.post('/api/auth/invitations',json={'email':'analyst@example.com','role':'analyst'}).json()['token']
        analyst=self.register('analyst@example.com',token)
        body={'key':key,'status':'resolved','comment':'Checked the source workbook.','version':0}
        self.assertEqual(analyst.put(f'/api/analysis/{aid}/finding',json=body).status_code,403)
        body['status']='investigating'
        self.assertEqual(analyst.put(f'/api/analysis/{aid}/finding',json=body).status_code,200)
        self.assertEqual(self.owner.put(f'/api/analysis/{aid}/finding',json=body).status_code,409)
        body.update(version=1,status='resolved',comment='')
        self.assertEqual(self.owner.put(f'/api/analysis/{aid}/finding',json=body).status_code,422)
        body['comment']='Verified supporting records.'
        self.assertEqual(self.owner.put(f'/api/analysis/{aid}/finding',json=body).status_code,200)
        final=self.owner.get(f'/api/analysis/{aid}/finding',params={'key':key}).json()
        self.assertEqual(final['review']['status'],'resolved')
        self.assertEqual(len(final['history']),2)
        self.assertEqual(final['evidence'],detail['evidence'])
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}/audit-report.pdf').status_code,200)
        analyst.close()

    def test_login_rate_limit_and_password_storage(self):
        from app.db.models import User
        with self.sessions() as db:
            stored = db.query(User).filter_by(email='owner@example.com').one().hashed_password
            self.assertTrue(stored.startswith('scrypt$'))
            self.assertNotIn('long-secure-test-passphrase', stored)
        client = TestClient(self.app)
        for _ in range(8):
            self.assertEqual(client.post('/api/auth/login', json={'email': 'missing@example.com', 'password': 'incorrect'}).status_code, 401)
        self.assertEqual(client.post('/api/auth/login', json={'email': 'missing@example.com', 'password': 'incorrect'}).status_code, 429)
        client.close()

    def test_running_cancel_stops_before_publishing_report(self):
        aid = self.upload()
        original = AnalysisService._run_rules
        def cancel_during_rules(service, frame):
            with self.sessions() as db:
                db.get(AnalysisJob, aid).cancel_requested = True
                db.commit()
            return original(service, frame)
        with patch.object(AnalysisService, '_run_rules', cancel_during_rules):
            self.assertTrue(run_once(self.sessions))
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}').json()['job']['state'], 'cancelled')
        self.assertEqual(self.owner.get(f'/api/analysis/{aid}/report').status_code, 409)

    def test_repeated_worker_interruptions_stop_at_attempt_limit(self):
        aid = self.upload()
        with self.sessions() as db:
            job = db.get(AnalysisJob, aid)
            job.state, job.attempts = 'running', 3
            job.lease_until = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
            db.commit()
            self.assertIsNone(claim(db))
            self.assertEqual(db.get(AnalysisJob, aid).state, 'failed')

if __name__=='__main__':
    unittest.main()
