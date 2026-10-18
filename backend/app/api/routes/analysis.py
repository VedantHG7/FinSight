from __future__ import annotations
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.security import Identity, current_identity, owned_analysis, require_role
from app.db.database import get_db
from app.db.models import Analysis, AnalysisJob, AnalysisStatus, Membership, FindingReview, ReviewEvent, User, AnalysisEvent
from app.services.analysis_service import AnalysisService, _artifact_json
from app.services.jobs import enqueue, job_data

router = APIRouter(prefix='/analysis', tags=['analysis'])


def ready(db, identity, analysis_id):
    analysis = owned_analysis(db, identity, analysis_id)
    if job_data(db, analysis)['state'] != 'completed':
        raise HTTPException(409, 'This analysis is not complete. Open its processing status.')
    return analysis


@router.post('/preview')
def preview_client(file: UploadFile = File(...), identity: Identity = Depends(current_identity)):
    require_role(identity, 'admin', 'analyst')
    from app.services.upload_preview import preview_upload
    return preview_upload(file)


@router.post('/upload', status_code=202)
def upload_client(file: UploadFile = File(...), preview_hash: str | None = Form(None), identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    require_role(identity, 'admin', 'analyst')
    if preview_hash is not None:
        from app.services.upload_preview import preview_upload
        preview = preview_upload(file)
        if not preview['valid'] or preview['file_hash'] != preview_hash:
            raise HTTPException(422, 'Workbook changed or contains invalid data. Preview it again before starting analysis.')
        file.file.seek(0)
    aid = enqueue(db, identity.user.id, file)
    return {'analysis_id': aid, 'state': 'queued'}


@router.get('')
def history(q: str = Query('', max_length=200), state: str = '', page: int = Query(1, ge=1), identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    from app.db.models import Client
    query = db.query(Analysis).join(Membership, Analysis.user_id == Membership.user_id).join(Client, Client.id == Analysis.client_id).filter(Membership.organization_id == identity.membership.organization_id)
    if q:
        pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.filter((Client.company_name.ilike(pattern, escape='\\')) | (Analysis.filename.ilike(pattern, escape='\\')))
    if state:
        query = query.outerjoin(AnalysisJob, Analysis.id == AnalysisJob.analysis_id)
        if state == 'completed':
            query = query.filter((AnalysisJob.state == state) | ((AnalysisJob.analysis_id == None) & (Analysis.status == AnalysisStatus.completed)))
        else:
            query = query.filter(AnalysisJob.state == state)
    total = query.count()
    rows = query.order_by(Analysis.created_at.desc(), Analysis.id.desc()).offset((page-1)*20).limit(20).all()
    service = AnalysisService(db)
    return {'total': total, 'page': page, 'items': [{**service.summary(a.id), 'job': job_data(db, a)} for a in rows]}


@router.get('/{analysis_id}')
def get_summary(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    analysis = owned_analysis(db, identity, analysis_id)
    return {**AnalysisService(db).summary(analysis_id), 'job': job_data(db, analysis)}


@router.post('/{analysis_id}/cancel')
def cancel(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    require_role(identity, 'admin', 'analyst')
    analysis = owned_analysis(db, identity, analysis_id)
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).with_for_update().first()
    if not job or job.state not in {'queued', 'running'}:
        raise HTTPException(409, 'Only queued or running analyses can be cancelled.')
    job.cancel_requested = True
    if job.state == 'queued':
        job.state, job.stage = 'cancelled', 'Cancelled'
    db.add(AnalysisEvent(analysis_id=analysis_id, stage='Cancellation', status='requested', message=f'Cancellation requested by {identity.user.full_name}.'))
    db.commit()
    return job_data(db, analysis)


@router.post('/{analysis_id}/retry')
def retry(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    require_role(identity, 'admin', 'analyst')
    analysis = owned_analysis(db, identity, analysis_id)
    job = db.query(AnalysisJob).filter_by(analysis_id=analysis_id).with_for_update().first()
    if not job or job.state not in {'failed', 'cancelled'}:
        raise HTTPException(409, 'Only failed or cancelled jobs can be retried.')
    job.state, job.stage, job.progress = 'queued', 'Queued', 0
    job.cancel_requested, job.attempts, job.error = False, 0, None
    job.lease_token, job.lease_until = None, None
    analysis.status = AnalysisStatus.uploaded
    db.add(AnalysisEvent(analysis_id=analysis_id, stage='Retry', status='queued', message=f'Retry requested by {identity.user.full_name}.'))
    db.commit()
    return job_data(db, analysis)


@router.get('/{analysis_id}/trail')
def trail(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    owned_analysis(db, identity, analysis_id)
    return AnalysisService(db).trail(analysis_id)


@router.get('/{analysis_id}/preprocessed.csv')
def csv(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    path = AnalysisService(db).artifact_path(analysis_id, 'preprocessed')
    if not path.exists():
        raise HTTPException(404, 'File not found.')
    return FileResponse(path, media_type='text/csv', filename=path.name, headers={'Cache-Control': 'no-store'})


@router.get('/{analysis_id}/audit-report.pdf')
def pdf(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    path = AnalysisService(db).artifact_path(analysis_id, 'pdf')
    if not path.exists():
        raise HTTPException(404, 'File not found.')
    return FileResponse(path, media_type='application/pdf', filename=path.name, headers={'Cache-Control': 'no-store'})


def findings(db, analysis_id):
    service = AnalysisService(db)
    rule_rows = service.rules(analysis_id).get('rows', [])
    result = [{'key': f"rule:{r['Year']}:{r['Rule ID']}", 'kind': 'rule', 'year': r['Year'], 'title': r['Rule Name'],
               'severity': r['Severity'], 'result': r['Status'], 'evidence': r} for r in rule_rows]
    for r in service.ml(analysis_id).get('rows', []):
        result.append({'key': f"ml:{r['Year']}", 'kind': 'ml', 'year': r['Year'], 'title': 'Machine-learning anomaly assessment',
                       'severity': 'Review' if r.get('Prediction') == 'Anomaly' else 'Info', 'result': r.get('Prediction'), 'evidence': r})
    return result


def review_value(row):
    return {'status': row.status, 'assignee_id': row.assignee_id, 'version': row.version} if row else {'status': 'open', 'assignee_id': None, 'version': 0}


@router.get('/{analysis_id}/findings')
def finding_list(analysis_id: int, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    reviews = {r.finding_key: r for r in db.query(FindingReview).filter_by(analysis_id=analysis_id)}
    return {'items': [{**{k: v for k, v in f.items() if k != 'evidence'}, 'review': review_value(reviews.get(f['key']))} for f in findings(db, analysis_id)]}


@router.get('/{analysis_id}/finding')
def finding_detail(analysis_id: int, key: str, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    item = next((f for f in findings(db, analysis_id) if f['key'] == key), None)
    if not item:
        raise HTTPException(404, 'Finding not found.')
    source = _artifact_json(AnalysisService(db)._root(analysis_id) / 'raw' / 'source_cells.json', {'cells': []})
    events = db.query(ReviewEvent, User).join(User, ReviewEvent.user_id == User.id).filter(ReviewEvent.analysis_id == analysis_id, ReviewEvent.finding_key == key).order_by(ReviewEvent.id).all()
    return {**item, 'review': review_value(db.get(FindingReview, (analysis_id, key))),
            'source_cells': [c for c in source['cells'] if c['year'] == item['year']],
            'history': [{'id': e.id, 'author': u.full_name, 'message': e.message, 'changes': json.loads(e.changes), 'created_at': e.created_at.isoformat()} for e, u in events]}


class ReviewInput(BaseModel):
    key: str = Field(max_length=160)
    status: Literal['open', 'investigating', 'resolved', 'accepted']
    assignee_id: int | None = None
    comment: str = Field(default='', max_length=4000)
    version: int = Field(ge=0)


@router.put('/{analysis_id}/finding')
def save_review(analysis_id: int, data: ReviewInput, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    if not any(f['key'] == data.key for f in findings(db, analysis_id)):
        raise HTTPException(404, 'Finding not found.')
    if data.assignee_id is not None:
        member = db.get(Membership, data.assignee_id)
        if not member or member.organization_id != identity.membership.organization_id:
            raise HTTPException(400, 'Assignee must belong to this workspace.')
    row = db.query(FindingReview).filter_by(analysis_id=analysis_id, finding_key=data.key).with_for_update().first()
    before = review_value(row)
    if data.status in {'resolved', 'accepted'} and before['status'] != data.status:
        require_role(identity, 'admin', 'reviewer')
    if before['version'] != data.version:
        raise HTTPException(409, 'Someone updated this finding. Reload its latest review before saving.')
    if data.status in {'resolved', 'accepted'} and before['status'] != data.status and not data.comment.strip():
        raise HTTPException(422, 'Add a review note explaining this decision.')
    if not row:
        row = FindingReview(analysis_id=analysis_id, finding_key=data.key, updated_by=identity.user.id)
        db.add(row)
    row.status, row.assignee_id, row.updated_by = data.status, data.assignee_id, identity.user.id
    row.version = data.version + 1
    changes = {'before': before, 'after': review_value(row)}
    db.add(ReviewEvent(analysis_id=analysis_id, finding_key=data.key, user_id=identity.user.id, message=data.comment.strip(), changes=json.dumps(changes)))
    db.add(AnalysisEvent(analysis_id=analysis_id, stage='Finding review', status=data.status, message=f'{identity.user.full_name} reviewed {data.key}.'))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Someone updated this finding. Reload and try again.')
    return review_value(row)


@router.get('/{analysis_id}/{view}')
def analysis_view(analysis_id: int, view: str, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    ready(db, identity, analysis_id)
    service = AnalysisService(db)
    methods = {'analysis': service.preprocessed, 'rules': service.rules, 'ml': service.ml, 'xai': service.xai, 'report': service.report}
    if view not in methods:
        raise HTTPException(404, 'Page not found.')
    return methods[view](analysis_id)
