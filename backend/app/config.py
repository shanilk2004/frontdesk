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
    _raw_db_url: str = os.getenv("DATABASE_URL", "sqlite:///./frontdesk.db")
    
    @property
    def DATABASE_URL(self) -> str:
        url = os.getenv("DATABASE_URL", self._raw_db_url)
        # Ensure postgresql+psycopg2 dialect driver if raw postgresql:// is provided
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

settings = Settings()
