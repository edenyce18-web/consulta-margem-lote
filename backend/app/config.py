from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Infraestrutura ────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/consulta_margem"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "TROQUE_ESTA_CHAVE_EM_PRODUCAO"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ── AkiCapital ────────────────────────────────────────────────────────────
    AKICAPITAL_URL: str = (
        "https://akipromotora.app/WebAutorizador/Login/AC.UI.LOGIN.aspx"
        "?FISession=7ed4824df157"
    )
    AKICAPITAL_LOGIN: str = "02622395230_901902"
    AKICAPITAL_SENHA: str = "Efetiva26*"

    # ── GridSoftware / Roraima ────────────────────────────────────────────────
    GRID_URL: str = "https://consignado.gridsoftware.com.br/grid/login.seam?"
    GRID_LOGIN: str = "02622395230"
    GRID_SENHA: str = "Manu@2025"

    # ── 2Captcha ──────────────────────────────────────────────────────────────
    TWOCAPTCHA_API_KEY: str = "7e42177042c9c211507f578edf43c6fb"
    TWOCAPTCHA_TIMEOUT_S: int = 120
    TWOCAPTCHA_POLL_INTERVAL_S: int = 5

    # ── Sessões Playwright ────────────────────────────────────────────────────
    SESSION_DIR: str = "/tmp/pw_sessions"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
