import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    EMAIL_SENDER = os.getenv("EMAIL_SENDER", "noreply@project-x.ink")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://project-y.project-x.ink")
    EMAIL_TOKEN_MAX_AGE = 3600
    EMAIL_RESEND_COOLDOWN = 60
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    AWS_REGION = os.getenv("AWS_REGION", "eu-central-1")

    DB_HOST = os.getenv("DB_HOST", "postgres")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "project_y")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
