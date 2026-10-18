from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.database import get_db
from app.db.models import AuthSession, Membership, User, Analysis

COOKIE = 'finsight_session'

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=32768, r=8, p=3, maxmem=64*1024*1024)
    return f'scrypt${salt}${value.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt, expected = encoded.split('$')
        if scheme != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=32768, r=8, p=3, maxmem=64*1024*1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def check_origin(request: Request):
    origin = request.headers.get('origin')
    if origin and origin not in settings.BACKEND_CORS_ORIGINS:
        raise HTTPException(403, 'Request origin is not allowed.')


@dataclass
class Identity:
    user: User
    membership: Membership
    session: AuthSession


def current_identity(request: Request, db: Session = Depends(get_db)) -> Identity:
    token = request.cookies.get(COOKIE, '')
    session = db.get(AuthSession, digest(token)) if token else None
    if not session or session.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        raise HTTPException(401, 'Please sign in to continue.')
    user = db.get(User, session.user_id)
    membership = db.get(Membership, session.user_id)
    if not user or not user.is_active or not membership:
        raise HTTPException(401, 'This account is unavailable.')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        check_origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf_token):
            raise HTTPException(403, 'Your session changed. Refresh the page and try again.')
    return Identity(user, membership, session)


def require_role(identity: Identity, *roles: str):
    if identity.membership.role not in roles:
        raise HTTPException(403, 'Your workspace role does not permit this action.')


def owned_analysis(db: Session, identity: Identity, analysis_id: int) -> Analysis:
    analysis = db.query(Analysis).join(Membership, Membership.user_id == Analysis.user_id).filter(
        Analysis.id == analysis_id, Membership.organization_id == identity.membership.organization_id).first()
    if not analysis:
        raise HTTPException(404, 'Analysis not found.')
    return analysis


def issue_session(db: Session, user: User, request: Request, response: Response):
    old = request.cookies.get(COOKIE)
    if old:
        db.query(AuthSession).filter_by(token_hash=digest(old)).delete()
    db.query(AuthSession).filter(AuthSession.expires_at < datetime.now(UTC).replace(tzinfo=None)).delete()
    token = secrets.token_urlsafe(32)
    session = AuthSession(token_hash=digest(token), user_id=user.id, csrf_token=secrets.token_hex(32),
                          expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=12))
    db.add(session)
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.COOKIE_SECURE, samesite='lax', max_age=43200, path='/api')
    response.headers['Cache-Control'] = 'no-store'
    return session
