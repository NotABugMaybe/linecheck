from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import settings
from .database import SessionLocal
from .models import User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
def hash_password(value: str) -> str: return pwd.hash(value)
def verify_password(value: str, hashed: str) -> bool: return pwd.verify(value, hashed)
def create_token(user: User) -> str:
    if not settings.secret_key: raise RuntimeError("SECRET_KEY must be configured")
    return jwt.encode({"sub": str(user.id), "org": user.organization_id, "exp": datetime.now(timezone.utc)+timedelta(minutes=settings.token_expiry_minutes)}, settings.secret_key, algorithm=ALGORITHM)
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def current_user(authorization: str | None = Header(default=None), db: Session=Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    try:
        payload=jwt.decode(authorization[7:], settings.secret_key, algorithms=[ALGORITHM])
        user=db.get(User,int(payload["sub"]))
        if not user or not user.active or user.organization_id != int(payload["org"]): raise ValueError()
        return user
    except (JWTError, ValueError, KeyError): raise HTTPException(401,"Invalid session")
def require_roles(*roles):
    def check(user: User=Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,"Insufficient role")
        return user
    return check
