from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Infraestrutura ────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/consulta_margem"
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Autenticação JWT ──────────────────────────────────────────────────────
    SECRET_KEY: str = "TROQUE_ESTA_CHAVE_EM_PRODUCAO"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15        # access token curto
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7           # refresh token longo

    # ── Criptografia de Credenciais (AES-256-GCM) ─────────────────────────────
    # Gere com: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
    ENCRYPTION_KEY: str = "TROQUE_32BYTES_BASE64_AQUI_OBRIGATORIO="

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://95.111.248.228:8080"

    # ── Rate Limiting de Login ────────────────────────────────────────────────
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 30

    # ── AkiCapital (defaults, sobrescritos pelas credenciais do usuário) ──────
    AKICAPITAL_URL: str = (
        "https://akipromotora.app/WebAutorizador/Login/AC.UI.LOGIN.aspx"
        "?FISession=7ed4824df157"
    )
    AKICAPITAL_LOGIN: str = ""
    AKICAPITAL_SENHA: str = ""

    # ── GridSoftware / Roraima ────────────────────────────────────────────────
    GRID_URL: str = "https://consignado.gridsoftware.com.br/grid/login.seam?"
    GRID_LOGIN: str = ""
    GRID_SENHA: str = ""

    # ── RF1Consig / Boa Vista ─────────────────────────────────────────────────
    RF1BV_URL: str = (
        "https://boavista.rf1consig.com.br/SGConsignataria/"
        "GESTOR/CADPessoaListar.aspx"
    )

    # ── 2Captcha ──────────────────────────────────────────────────────────────
    TWOCAPTCHA_API_KEY: str = ""
    TWOCAPTCHA_TIMEOUT_S: int = 120
    TWOCAPTCHA_POLL_INTERVAL_S: int = 5

    # ── Sessões Playwright ────────────────────────────────────────────────────
    SESSION_DIR: str = "/tmp/pw_sessions"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
