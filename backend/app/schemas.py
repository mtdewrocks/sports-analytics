from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserRegister(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: str
    trial_ends_at: datetime
    created_at: datetime
    model_config = {"from_attributes": True}

class TokenWithUser(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class BillingStatus(BaseModel):
    status: str
    trial_ends_at: datetime
    days_remaining: int
    subscription_status: Optional[str] = None
    current_period_end: Optional[datetime] = None
