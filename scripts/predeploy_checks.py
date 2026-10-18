"""Run real PostgreSQL/API/worker/browser checks without using the local app data.

Run from the project root with backend/.venv/Scripts/python.exe on Windows.
Requires PostgreSQL credentials in backend/.env, Node, Edge and dependencies.
Ports 8000 and 5173 must be free. Creates and removes its own temporary database.
"""
from datetime import datetime, UTC
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / 'backend')
sys.path.insert(0, str(ROOT / 'backend'))
import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.config import settings


def main():
    for port in (8000, 5173):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'Port {port} is in use; refusing to stop an existing service.')
    tag = datetime.now(UTC).strftime('%Y%m%d%H%M%S') + '_' + secrets.token_hex(3)
    name = 'finsight_qa_' + tag
    output = ROOT / 'output' / 'predeploy' / tag
    output.mkdir(parents=True)
    url = make_url(settings.DATABASE_URL)
    admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    env = dict(os.environ, DATABASE_URL=url.set(database=name).render_as_string(hide_password=False),
               ANALYSIS_WORKSPACE_PATH=str(output / 'artifacts'), STORAGE_BASE_PATH=str(output / 'storage'),
               COOKIE_SECURE='false', PUBLIC_APP_URL='http://127.0.0.1:5173',
               BACKEND_CORS_ORIGINS='["http://127.0.0.1:5173"]', SMTP_HOST='', SMTP_PASSWORD='',
               TEMP=str(ROOT / 'tmp'), TMP=str(ROOT / 'tmp'),
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', NUMBA_NUM_THREADS='1')
    processes, logs = [], []
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    def start(label, args, cwd):
        log = (output / (label + '.log')).open('a', encoding='utf-8')
        logs.append(log)
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=flags)
        processes.append(process)
        return process

    def ready(address, process):
        for _ in range(90):
            if process.poll() is not None:
                raise RuntimeError(f'Service exited; inspect {output}')
            try:
                if httpx.get(address, timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise RuntimeError(f'Service did not become ready: {address}')

    def stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    try:
        api_args = [sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000']
        api = start('api', api_args, ROOT / 'backend')
        ready('http://127.0.0.1:8000/api/health', api)
        worker = start('worker', [sys.executable, '-m', 'app.worker'], ROOT / 'backend')
        node = shutil.which('node')
        web = start('web', [node, 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort'], ROOT / 'frontend')
        ready('http://127.0.0.1:5173/', web)
        for test in ('upload-preview.smoke.mjs', 'analytics-units.smoke.mjs', 'workspace.smoke.mjs'):
            subprocess.run([node, 'tests/' + test], cwd=ROOT / 'frontend', env=env, check=True, timeout=300)
            print('PASS browser:', test, flush=True)

        with httpx.Client(base_url='http://127.0.0.1:5173/api', timeout=60) as client:
            response = client.post('/auth/register', json={'email': f'restart-{tag}@example.com',
                'password': secrets.token_urlsafe(24), 'full_name': 'Restart QA', 'organization': 'Isolated QA'})
            response.raise_for_status()
            client.headers['X-CSRF-Token'] = response.json()['csrf_token']
            sample = ROOT / 'backend/tests/fixtures/legacy_sample.xls'
            response = client.post('/analysis/upload', files={'file': ('legacy.xls', sample.read_bytes())})
            response.raise_for_status()
            aid = response.json()['analysis_id']
            for _ in range(120):
                response = client.get(f'/analysis/{aid}')
                response.raise_for_status()
                state = response.json()['job']['state']
                if state == 'completed':
                    break
                if state in ('failed', 'cancelled'):
                    raise RuntimeError(f'Legacy workbook failed: {response.text}')
                time.sleep(2)
            else:
                raise RuntimeError('Legacy workbook did not finish within four minutes')
            pdf = client.get(f'/analysis/{aid}/audit-report.pdf')
            pdf.raise_for_status()
            assert pdf.content.startswith(b'%PDF'), 'Invalid PDF download'
            (output / 'verified-report.pdf').write_bytes(pdf.content)
            checksum = hashlib.sha256(pdf.content).hexdigest()
            csv = client.get(f'/analysis/{aid}/preprocessed.csv')
            csv.raise_for_status()
            assert 'Sales' in csv.text, 'CSV is missing source metrics'
            stop(worker)
            stop(api)
            api = start('api', api_args, ROOT / 'backend')
            ready('http://127.0.0.1:8000/api/health', api)
            worker = start('worker', [sys.executable, '-m', 'app.worker'], ROOT / 'backend')
            client.get('/auth/me').raise_for_status()
            restored = client.get(f'/analysis/{aid}/audit-report.pdf')
            restored.raise_for_status()
            assert hashlib.sha256(restored.content).hexdigest() == checksum
            print('PASS: real PostgreSQL XLS job, PDF/CSV download, session and report persistence after API/worker restart', flush=True)
        print(f'PASS: integration suite. Logs and sample report: {output}', flush=True)
    finally:
        for process in reversed(processes):
            stop(process)
        for log in logs:
            log.close()
        # Only the database created above is removed; the local app DB is untouched.
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == '__main__':
    main()
