from sqlalchemy import Column, Integer, String, DateTime, JSON
from .database import Base
import datetime

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String, unique=True, index=True)
    session_id = Column(String)
    uid = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class TaskRecord(Base):
    __tablename__ = "task_records"

    id = Column(String, primary_key=True, index=True) # UUID
    filename = Column(String)
    status = Column(String) # pending, running, completed, stopped, failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    log_path = Column(String)
    stats = Column(JSON, nullable=True) # {total: 0, sent: 0, failed: 0}

class SystemConfig(Base):
    __tablename__ = "system_config"
    key = Column(String, primary_key=True, index=True)
    value = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
