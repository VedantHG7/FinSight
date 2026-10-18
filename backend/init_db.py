"""
Initialize the database by creating all tables and seeding required data.
"""
from app.db.database import engine, SessionLocal
from app.db.models import Base, User, Client, UserRole

# Import all models to ensure they are registered with Base
from app.db import models  # noqa

def init_db():
    """Create all tables and seed required default records."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")

    # Seed default user and client so uploads don't hit FK violations
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.id == 1).first():
            db.add(User(
                id=1,
                email="admin@finsight.io",
                hashed_password="not-a-real-hash",
                full_name="System Admin",
                role=UserRole.ADMIN,
            ))
            db.commit()
            print("Seeded default user (id=1).")

        if not db.query(Client).filter(Client.id == 1).first():
            db.add(Client(
                id=1,
                user_id=1,
                company_name="Default Client",
            ))
            db.commit()
            print("Seeded default client (id=1).")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()