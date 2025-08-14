import sqlite3
# import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


SQLALCHEMY_DATABASE_URL = "postgresql://db_nursement_user:qh0pQoOXf66DK0d5LUyKSLHYYoze5xpZ@dpg-cle36h6f27hc738pm570-a.singapore-postgres.render.com/db_reorder_reminder_pro_stg"
# engine=create_engine(SQLALCHEMY_DATABASE_URL)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,            # Number of persistent connections
    max_overflow=40,         # Extra connections if pool is full
    pool_timeout=30,         # Max wait time for a connection
    pool_recycle=280,        # Recycle connections before idle timeout (~5 min safe default)
    pool_pre_ping=True,      # Check if connection is alive before using it
    echo_pool=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
