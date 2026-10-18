"""Durable database queue, with a dedicated worker (python -m app.worker)."""
from datetime import UTC, datetime, timedelta
import hashlib
import logging
from pathlib import Path
import secrets
import threading
import zipfile

from fastapi import HTTPException
from sqlalchemy import or_, and_, text
from app.core.config import settings
from app.db.database import SessionLocal, engine
from app.db.models import Analysis, AnalysisStatus, AnalysisJob, Client, Membership, AnalysisEvent
from app.services.analysis_service import AnalysisService

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3

class InterruptedJob(Exception):
    pass


def enqueue(db, user_id, upload):
    filename = (upload.filename or 'workbook.xlsx').replace('\\', '/').split('/')[-1][:240]
    suffix = Path(filename).suffix.lower()
    if suffix not in {'.xlsx', '.xls'}:
        raise HTTPException(400, 'Choose an Excel workbook (.xlsx or .xls).')
    root = Path(settings.ANALYSIS_WORKSPACE_PATH)
    incoming = root / 'incoming'
    incoming.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(24)
    path = incoming / (token + suffix)
    size = 0
    fingerprint = hashlib.sha256()
    try:
        with path.open('wb') as out:
            while chunk := upload.file.read(65536):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_SIZE:
                    raise HTTPException(413, 'Workbook exceeds the 10 MB upload limit.')
                fingerprint.update(chunk)
                out.write(chunk)
        with path.open('rb') as source:
            signature = source.read(8)
        if suffix == '.xlsx':
            if not zipfile.is_zipfile(path):
                raise HTTPException(400, 'The file is not a valid XLSX workbook.')
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(e.file_size for e in entries) > 100*1024*1024:
                    raise HTTPException(413, 'The expanded workbook is too large.')
                if 'xl/workbook.xml' not in archive.namelist():
                    raise HTTPException(400, 'The file is not a valid XLSX workbook.')
        elif signature != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
            raise HTTPException(400, 'The file is not a valid XLS workbook.')
        # Pending client is visible only until the worker reads the company name.
        client = db.query(Client).filter_by(user_id=user_id, company_name='Pending validation').first()
        if not client:
            client = Client(user_id=user_id, company_name='Pending validation')
            db.add(client)
            db.flush()
        analysis = Analysis(user_id=user_id, client_id=client.id, filename=filename,
                            file_path=str(path.resolve()), status=AnalysisStatus.uploaded)
        db.add(analysis)
        db.flush()
        db.add(AnalysisJob(analysis_id=analysis.id, file_hash=fingerprint.hexdigest()))
        db.add(AnalysisEvent(analysis_id=analysis.id, stage='Upload', status='queued', message='Workbook accepted and queued.'))
        db.commit()
        return analysis.id
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise


def job_data(db, analysis):
    job = db.get(AnalysisJob, analysis.id)
    if not job:
        return {'state': 'completed' if analysis.status == AnalysisStatus.completed else 'failed',
                'progress': 100 if analysis.status == AnalysisStatus.completed else 0,
                'stage': 'Legacy analysis', 'error': None, 'attempts': 0, 'cancel_requested': False}
    return {key: getattr(job, key) for key in ('state', 'stage', 'progress', 'error', 'attempts', 'cancel_requested')}


def claim(db):
    now = datetime.now(UTC).replace(tzinfo=None)
    job = db.query(AnalysisJob).filter(or_(AnalysisJob.state == 'queued', and_(AnalysisJob.state == 'running', AnalysisJob.lease_until < now))).order_by(AnalysisJob.created_at).with_for_update(skip_locked=True).first()
    if not job:
        return None
    if job.cancel_requested or job.attempts >= MAX_ATTEMPTS:
        job.state = 'cancelled' if job.cancel_requested else 'failed'
        job.stage = job.state.title()
        job.error = None if job.cancel_requested else 'Worker interrupted repeatedly. Retry this analysis from history.'
        db.commit()
        return None
    job.state = 'running'
    job.attempts += 1
    job.lease_token = secrets.token_hex(24)
    job.lease_until = now + timedelta(seconds=90)
    job.error = None
    job.stage = 'Starting analysis'
    job.progress = 0
    db.commit()
    return job.analysis_id, job.lease_token


def run_once(sessions=SessionLocal):
    # A PostgreSQL advisory lock serializes workers through restarts and long ML stages.
    # The lease remains useful for detecting and displaying interrupted jobs.
    with sessions() as db:
        bind = db.get_bind()
    lock_connection = bind.connect() if bind.dialect.name == 'postgresql' else None
    if lock_connection is not None and not lock_connection.execute(text('SELECT pg_try_advisory_lock(74639121)')).scalar():
        lock_connection.close()
        return False
    try:
        with sessions() as db:
            claimed = claim(db)
        if not claimed:
            return False
        analysis_id, token = claimed
        stop = threading.Event()

        def checkpoint(stage=None, progress=None):
            with sessions() as db:
                job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).with_for_update().one()
                if job.lease_token != token or job.state != 'running' or job.cancel_requested:
                    raise InterruptedJob()
                job.lease_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=90)
                if stage is not None:
                    job.stage, job.progress = stage, progress
                db.commit()

        def heartbeat():
            while not stop.wait(20):
                try:
                    checkpoint()
                except Exception:
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            with sessions() as db:
                AnalysisService(db, checkpoint=checkpoint).process_analysis(analysis_id)
            checkpoint('Completed', 100)
            state, error = 'completed', None
        except InterruptedJob:
            state, error = 'cancelled', None
        except Exception:
            log.exception('Analysis %s failed', analysis_id)
            state, error = 'failed', 'The workbook could not be processed. Check its Data Sheet and financial values, then retry or upload a corrected workbook.'
        finally:
            stop.set()
            thread.join(timeout=2)
        with sessions() as db:
            job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).with_for_update().one()
            if job.lease_token == token:
                if job.cancel_requested:
                    state, error = 'cancelled', None
                job.state, job.error, job.stage = state, error, state.title()
                job.lease_until = None
                analysis = db.get(Analysis, analysis_id)
                analysis.status = AnalysisStatus.completed if state == 'completed' else AnalysisStatus.failed
                db.add(AnalysisEvent(analysis_id=analysis_id, stage='Worker', status=state, message=error or f'Analysis {state}.'))
                db.commit()
        return True
    finally:
        if lock_connection is not None:
            try:
                lock_connection.execute(text('SELECT pg_advisory_unlock(74639121)'))
            finally:
                lock_connection.close()
