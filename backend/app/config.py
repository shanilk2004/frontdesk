import os
from pathlib import Path

# Load .env file if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./frontdesk.db")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

settings = Settings()
