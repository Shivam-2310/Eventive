from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    DATABASE_URL: str = "sqlite:///./data/flo.db"
    DATA_DIR: str = "./data"
    PORT: int = 8000

    # Chat/completion LLM (used by FloBot, NL2SQL, recommendation reasons).
    # Options: "stub" (deterministic, offline), "gemini", "groq".
    # The LangChain Ask Flo agent (app/domain/ai/agent.py) picks its provider
    # in this order regardless of LLM_PROVIDER: Groq (if GROQ_API_KEY is set)
    # → Gemini (if GEMINI_API_KEY is set) → deterministic regex fallback.
    LLM_PROVIDER: str = "stub"
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-2.5-flash"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # Embedding provider — always runs locally by default. Options:
    #   "local" → LocalEmbedProvider (ONNX via fastembed, no network)
    #   "stub"  → deterministic SHA-256 vectors (only for tests / broken envs)
    # The dimension of EMBED_MODEL_NAME must match app.domain.ai.llm_provider.EMBED_DIM
    # (currently 384) AND the sqlite-vec table dimension in Alembic 004.
    EMBED_PROVIDER: str = "local"
    EMBED_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"

    CORS_ORIGINS: str = "*"

    JWT_SECRET: str = "dev-only-not-a-real-secret"
    JWT_ALG: str = "HS256"
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 7

    ADMIN_EMAIL: str = "admin@flo.dev"
    ADMIN_INITIAL_PASSWORD: str = "admin"

    MEDIA_SIGNING_SECRET: str = "dev-media-secret"
    MEDIA_URL_TTL_SECONDS: int = 600

    SEED_DEMO_FIXTURES: bool = True

    # Directory containing the built Flutter web bundle (index.html, main.dart.js, ...).
    # Empty string => don't mount any static frontend (backend-only mode, e.g. local dev
    # where the Flutter app is running separately on port 3000).
    FRONTEND_WEB_DIR: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.CORS_ORIGINS.strip()
        if raw in ("", "*"):
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
