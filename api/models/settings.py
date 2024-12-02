from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

    sbat_username: str
    sbat_password: str

    stripe_secret_key: str | None = None
    stripe_publishable_key: str | None = None
    stripe_endpoint_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    discord_bot_token: str | None
    discord_guild_id: str | None
    discord_channel_id: str | None = None
    discord_public_key: str | None = None

    sender_email: str | None = None
    sender_password: str | None = None
    smtp_server: str | None = None
    smtp_port: int | None = None

    jwt_secret_key: str
    access_token_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"

    class Config:
        env_file: str = ".env"
