import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import models
from database import get_db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Config ---
# SECRET_KEY must come from the environment. We deliberately do NOT provide a
# hardcoded fallback — if it's missing, the app should fail to start rather
# than silently run with a secret an attacker could read from source control.
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Role-aware current-user resolvers

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Return (role, user_object) for any valid token."""
    payload = decode_token(token)
    role = payload.get("role")
    user_id = payload.get("sub")
    if not role or not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    if role == "patient":
        user = db.query(models.Patient).filter(models.Patient.id == int(user_id)).first()
    elif role == "chw":
        user = db.query(models.CHW).filter(models.CHW.id == int(user_id)).first()
    elif role == "dietician":
        user = db.query(models.Dietician).filter(models.Dietician.id == int(user_id)).first()
    elif role == "doctor":
        user = db.query(models.Doctor).filter(models.Doctor.id == int(user_id)).first()
    else:
        raise HTTPException(status_code=401, detail="Unknown role")

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return role, user


def require_patient(current=Depends(get_current_user)):
    role, user = current
    if role != "patient":
        raise HTTPException(status_code=403, detail="Patients only")
    return user


def require_chw(current=Depends(get_current_user)):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor access required")
    return user


def require_doctor(current=Depends(get_current_user)):
    role, user = current
    if role != "doctor":
        raise HTTPException(status_code=403, detail="Doctors only")
    return user


def require_dietician(current=Depends(get_current_user)):
    role, user = current
    if role not in ("dietician", "doctor"):
        raise HTTPException(status_code=403, detail="Dietician or Doctor access required")
    return user


def require_diet_access(current=Depends(get_current_user)):
    """A Dietician is scoped ONLY to diet plans, food logs, and the exercise plan.
    CHW and Doctor can also manage these. Use this instead of require_chw on any
    endpoint that touches diet/exercise so Dieticians can reach it too."""
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Dietician, or Doctor access required")
    return user
