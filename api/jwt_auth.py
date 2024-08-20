from datetime import datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from passlib.context import CryptContext
from pymongo.results import UpdateResult

from .dependencies import Settings, get_current_user, get_db, get_settings
from .models import MonitorPreferences, SubscriberCreate, SubscriberRead

auth = APIRouter(prefix="/auth", tags=["Authentication"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def authenticate_user(username: str, password: str, db: AsyncIOMotorDatabase) -> SubscriberRead | None:

    subscriber: dict | None = await db["subscribers"].find_one({"email": username})
    print(subscriber, username, password)

    if not subscriber:
        return

    print(subscriber)
    if not pwd_context.verify(password, subscriber.get("hashed_password")):
        return

    return SubscriberRead(**subscriber)


def create_access_token(data: dict, settings: Settings) -> str:
    to_encode: dict = data.copy()
    expire: datetime = datetime.now() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@auth.post("/subscribe")
async def subscribe(subscriber: SubscriberCreate, db: AsyncIOMotorDatabase = Depends(get_db)) -> dict[str, str]:
    existing_subscriber: dict | None = await db["subscribers"].find_one({"email": subscriber.email})
    if existing_subscriber:
        raise HTTPException(status_code=400, detail="Email already subscribed")

    await db["subscribers"].insert_one({**subscriber.model_dump(), "hashed_password": pwd_context.hash(subscriber.password)})
    return {"message": "Subscribed successfully!"}


@auth.post("/token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncIOMotorDatabase = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    subscriber: SubscriberRead | None = await authenticate_user(form_data.username, form_data.password, db)
    if not subscriber:
        raise HTTPException(status_code=401, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})

    access_token: str = create_access_token(data={"sub": subscriber.email}, settings=settings)
    return {"access_token": access_token, "token_type": "bearer"}


@auth.get("/user/me")
async def read_users_me(current_user: SubscriberRead = Depends(get_current_user)) -> SubscriberRead:
    return current_user


@auth.get("/user/preferences")
async def update_users_monitoring_preferences(
    preferences: MonitorPreferences, current_user=Depends(get_current_user), db: AsyncIOMotorDatabase = Depends(get_db)
) -> SubscriberRead:
    result: UpdateResult = await db["subscribers"].update_one(
        {"_id": current_user._id}, {"$set": {"monitoring_preferences": {**preferences.model_dump()}}}  # pylint:disable=protected-access
    )
    if result.modified_count == 1:
        return {"detail": "Preferences saved!"}
    raise HTTPException(
        status_code=500,
        detail="Error occured during preference update.",
    )