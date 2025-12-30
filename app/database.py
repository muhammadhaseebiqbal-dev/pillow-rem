"""
Database configuration using SQLAlchemy with SQLite.
Stores original and processed images as file paths.
"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Create database directory if it doesn't exist
DATABASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATABASE_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{os.path.join(DATABASE_DIR, 'images.db')}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ImageRecord(Base):
    """Model to store image records with original and processed versions."""
    __tablename__ = "images"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    original_path = Column(String, nullable=False)
    processed_path = Column(String, nullable=False)
    original_size = Column(Integer)  # in bytes
    processed_size = Column(Integer)  # in bytes
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "original_path": self.original_path,
            "processed_path": self.processed_path,
            "original_size": self.original_size,
            "processed_size": self.processed_size,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
