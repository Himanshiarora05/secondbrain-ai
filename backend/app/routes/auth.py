"""Sign-up, login, logout and the current user (see app/services/auth_service.py)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.user import User
from app.services import auth_service as auth

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

BAD_LOGIN = "Email or password is incorrect."


class Credentials(BaseModel):
    email: str
    password: str


def _user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email}


def _start_session(response: Response, db: Session, user: User) -> dict:
    token = auth.create_session(db, user)
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=auth.SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=auth.cookie_secure(),
        path="/",
    )
    # The token is also returned for scripts that use "Authorization: Bearer";
    # the browser app relies on the HttpOnly cookie and never reads it.
    return {"user": _user_dict(user), "token": token}


@router.post("/signup", status_code=201)
def signup(body: Credentials, response: Response, db: Session = Depends(get_db)):
    if not auth.signup_allowed():
        raise HTTPException(status_code=403, detail="Sign-up is closed. Ask the owner of this SecondBrain for access.")
    email = auth.normalize_email(body.email)
    problem = auth.check_email(email) or auth.check_password(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists. Log in instead.")
    user = User(email=email, password_hash=auth.hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # the same email signed up at the same moment
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Log in instead.")
    db.refresh(user)
    return _start_session(response, db, user)


@router.post("/login")
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == auth.normalize_email(body.email)).first()
    # One message for an unknown email and a wrong password, and the same bcrypt
    # cost for both, so neither the reply nor its timing says which it was.
    if not auth.verify_password(body.password, user.password_hash if user else None):
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    return _start_session(response, db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.end_session(db, auth.token_from_request(request))
    response.delete_cookie(auth.SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=auth.cookie_secure())
    return {"message": "Logged out."}


@router.get("/me")
def me(user: User = Depends(auth.get_current_user)):
    return {"user": _user_dict(user), "signup_allowed": auth.signup_allowed()}
