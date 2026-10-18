from datetime import UTC, datetime, timedelta
import logging
import re
import secrets
import smtplib
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.security import (COOKIE, Identity, check_origin, current_identity, digest, hash_password,
                               issue_session, require_role, verify_password)
from app.core.config import settings
from app.core.mail import send_password_reset
from app.db.database import get_db
from app.db.models import User, Organization, Membership, AuthSession, Invitation, LoginAttempt, PasswordReset

router = APIRouter(prefix='/auth', tags=['accounts'])

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)

class Registration(Credentials):
    full_name: str = Field(min_length=2, max_length=120)
    organization: str = Field(default='', max_length=160)
    invite_token: str = Field(default='', max_length=128)

class InviteInput(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: Literal['admin', 'analyst', 'reviewer'] = 'analyst'


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPassword(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=256)


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


def email_address(value):
    email = value.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Enter a valid email address.')
    return email


def throttle(db, request, email, purpose='login', per_identity=8, per_address=40):
    now = datetime.now(UTC).replace(tzinfo=None)
    address = digest(purpose + ':' + (request.client.host if request.client else 'unknown'))
    identity = digest(purpose + ':' + email)
    since = now - timedelta(minutes=15)
    # Persist failed attempts so restarting the API does not reset the limit.
    if db.query(LoginAttempt).filter(LoginAttempt.created_at > since, LoginAttempt.identity == identity).count() >= per_identity or db.query(LoginAttempt).filter(LoginAttempt.created_at > since, LoginAttempt.address == address).count() >= per_address:
        raise HTTPException(429, 'Too many attempts. Try again in 15 minutes.')
    db.query(LoginAttempt).filter(LoginAttempt.created_at < since).delete()
    db.add(LoginAttempt(identity=identity, address=address, created_at=now))
    db.commit()


def payload(db, user, session):
    membership = db.get(Membership, user.id)
    organization = db.get(Organization, membership.organization_id)
    return {'user': {'id': user.id, 'email': user.email, 'name': user.full_name, 'role': membership.role},
            'organization': {'id': organization.id, 'name': organization.name}, 'csrf_token': session.csrf_token}


@router.post('/register', status_code=201)
def register(data: Registration, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    email = email_address(data.email)
    throttle(db, request, email)
    if len(data.password) < 12:
        raise HTTPException(422, 'Use a password with at least 12 characters.')
    if not data.full_name.strip():
        raise HTTPException(422, 'Enter your name.')
    invite = None
    if data.invite_token:
        invite = db.query(Invitation).filter_by(token_hash=digest(data.invite_token)).with_for_update().first()
        if not invite or invite.used or invite.expires_at < datetime.now(UTC).replace(tzinfo=None) or invite.email != email:
            raise HTTPException(400, 'This invitation is invalid, expired, or for a different email.')
        organization_id, role = invite.organization_id, invite.role
    else:
        if not data.organization.strip():
            raise HTTPException(422, 'Enter a workspace name.')
        organization = Organization(name=data.organization.strip())
        db.add(organization)
        db.flush()
        organization_id, role = organization.id, 'admin'
    user = User(email=email, hashed_password=hash_password(data.password), full_name=data.full_name.strip())
    try:
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=organization_id, role=role))
        if invite:
            invite.used = True
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Unable to register this email. Try signing in instead.')
    session = issue_session(db, user, request, response)
    return payload(db, user, session)


@router.post('/login')
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    email = email_address(data.email)
    throttle(db, request, email)
    user = db.query(User).filter_by(email=email).first()
    # Perform equivalent expensive work for unknown users.
    valid = verify_password(data.password, user.hashed_password) if user else verify_password(data.password, 'scrypt$dummy$' + '0'*128)
    if not valid or not user.is_active or not db.get(Membership, user.id):
        raise HTTPException(401, 'Email or password is incorrect.')
    db.query(LoginAttempt).filter_by(identity=digest('login:' + email)).delete()
    session = issue_session(db, user, request, response)
    return payload(db, user, session)


@router.get('/me')
def me(response: Response, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return payload(db, identity.user, identity.session)


@router.post('/logout')
def logout(response: Response, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    db.delete(identity.session)
    db.commit()
    response.delete_cookie(COOKIE, path='/api')
    return {'ok': True}


@router.post('/forgot-password', status_code=202)
def forgot_password(data: ResetRequest, request: Request, db: Session = Depends(get_db)):
    check_origin(request)
    email = email_address(data.email)
    throttle(db, request, email, purpose='reset', per_identity=3, per_address=20)
    if (not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL or
            (settings.SMTP_USERNAME and not settings.SMTP_PASSWORD) or
            not settings.PUBLIC_APP_URL.startswith(('https://', 'http://'))):
        raise HTTPException(503, 'Password recovery is not configured. Contact your administrator.')
    user = db.query(User).filter_by(email=email, is_active=True).first()
    if user and db.get(Membership, user.id):
        now = datetime.now(UTC).replace(tzinfo=None)
        db.query(PasswordReset).filter_by(user_id=user.id).delete()
        token = secrets.token_urlsafe(32)
        reset = PasswordReset(token_hash=digest(token), user_id=user.id, expires_at=now + timedelta(minutes=30))
        db.add(reset)
        db.commit()
        url = settings.PUBLIC_APP_URL.rstrip('/') + '/reset-password?token=' + quote(token, safe='')
        try:
            send_password_reset(email, url)
        except (OSError, smtplib.SMTPException):
            logging.getLogger(__name__).exception('Password reset email delivery failed')
            db.delete(reset)
            db.commit()
            raise HTTPException(503, 'Password recovery is temporarily unavailable. Try again later.')
    return {'message': 'If an active account exists for that email, a reset link has been sent.'}


@router.post('/reset-password')
def reset_password(data: ResetPassword, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    reset = db.query(PasswordReset).filter_by(token_hash=digest(data.token)).with_for_update().first()
    now = datetime.now(UTC).replace(tzinfo=None)
    if not reset or reset.expires_at <= now:
        raise HTTPException(400, 'This reset link is invalid or expired. Request a new link.')
    user = db.get(User, reset.user_id)
    if not user or not user.is_active or not db.get(Membership, user.id):
        raise HTTPException(400, 'This reset link is invalid or expired. Request a new link.')
    user.hashed_password = hash_password(data.password)
    db.query(PasswordReset).filter_by(user_id=user.id).delete()
    db.query(AuthSession).filter_by(user_id=user.id).delete()
    db.commit()
    response.delete_cookie(COOKIE, path='/api')
    return {'message': 'Password updated. Sign in with your new password.'}


@router.post('/change-password')
def change_password(data: ChangePassword, request: Request, response: Response, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    throttle(db, request, identity.user.email, purpose='change')
    if not verify_password(data.current_password, identity.user.hashed_password):
        raise HTTPException(400, 'Current password is incorrect.')
    identity.user.hashed_password = hash_password(data.new_password)
    db.query(PasswordReset).filter_by(user_id=identity.user.id).delete()
    db.query(AuthSession).filter_by(user_id=identity.user.id).delete()
    db.commit()
    response.delete_cookie(COOKIE, path='/api')
    return {'message': 'Password updated. Sign in with your new password.'}


@router.get('/members')
def members(identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    rows = db.query(User, Membership).join(Membership, User.id == Membership.user_id).filter(Membership.organization_id == identity.membership.organization_id).all()
    return [{'id': u.id, 'name': u.full_name, 'email': u.email, 'role': m.role} for u, m in rows]


@router.post('/invitations', status_code=201)
def invite(data: InviteInput, identity: Identity = Depends(current_identity), db: Session = Depends(get_db)):
    require_role(identity, 'admin')
    email = email_address(data.email)
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, 'This email already has an account. Use a new team member email.')
    token = secrets.token_urlsafe(32)
    db.add(Invitation(token_hash=digest(token), organization_id=identity.membership.organization_id,
                      email=email, role=data.role, expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=3)))
    db.commit()
    return {'token': token, 'expires_in_days': 3}
