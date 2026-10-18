"""Explicit, local-only migration of pre-account development analyses.
Usage: python -m app.import_legacy --email owner@example.com
"""
import argparse
from app.db.database import SessionLocal, create_tables
from app.db.models import User, Membership, Analysis, Client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    args = parser.parse_args()
    create_tables()
    with SessionLocal() as db:
        owner = db.query(User).filter_by(email=args.email.strip().lower()).first()
        member = db.get(Membership, owner.id) if owner else None
        if not member or member.role != 'admin':
            parser.error('Create the destination workspace admin account first.')
        legacy = db.query(User).filter_by(email='audit@finsight.local', hashed_password='local-dev').first()
        if not legacy:
            print('No legacy development account to import.')
            return
        count = db.query(Analysis).filter_by(user_id=legacy.id).update({'user_id': owner.id})
        db.query(Client).filter_by(user_id=legacy.id).update({'user_id': owner.id})
        legacy.is_active = False
        db.commit()
        print(f'Imported {count} analyses into the selected workspace. Original files are unchanged.')

if __name__ == '__main__':
    main()
