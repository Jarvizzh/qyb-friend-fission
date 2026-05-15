from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class LoginRequest(BaseModel):
    mobile: str
    password: str

class UserSessionSchema(BaseModel):
    mobile: str
    uid: str
    updated_at: datetime

    class Config:
        from_attributes = True

class TaskPreview(BaseModel):
    sender: str
    tag: str
    receiver: str
    internal: bool
    start: int
    limit: int

class TaskCreate(BaseModel):
    tasks: List[TaskPreview]

class SecretVerifyRequest(BaseModel):
    secret_key: str

class TaskResponse(BaseModel):
    id: str
    filename: str
    status: str
    created_at: datetime
    stats: Optional[dict] = None

    class Config:
        from_attributes = True
