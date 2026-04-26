#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  SETUP - ConsultaMargem VPS"
echo "============================================"
echo ""

# ── 1. Atualiza sistema ───────────────────────────────────────────────────────
echo "[1/6] Atualizando sistema..."
apt-get update -qq && apt-get upgrade -y -qq
echo "      OK!"

# ── 2. Instala Docker ─────────────────────────────────────────────────────────
echo "[2/6] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "      Docker instalado!"
else
    echo "      Docker ja instalado, pulando."
fi

# ── 3. Instala Docker Compose plugin ─────────────────────────────────────────
echo "[3/6] Verificando Docker Compose..."
if ! docker compose version &> /dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi
docker compose version
echo "      OK!"

# ── 4. Clona o projeto ────────────────────────────────────────────────────────
echo "[4/6] Clonando projeto..."
if [ -d "/opt/consulta-margem" ]; then
    echo "      Pasta ja existe, atualizando..."
    cd /opt/consulta-margem
    git pull
else
    git clone https://edenyce18-web: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@github.com/edenyce18-web/consulta-margem-lote.git /opt/consulta-margem
    cd /opt/consulta-margem
fi
echo "      OK!"

# ── 5. Cria arquivo .env com credenciais ──────────────────────────────────────
echo "[5/6] Configurando credenciais..."
cat > /opt/consulta-margem/backend/.env << 'ENVFILE'
# Infraestrutura
DATABASE_URL=postgresql://postgres:postgres@db:5432/consulta_margem
REDIS_URL=redis://redis:6379/0
SECRET_KEY=cM9xP2vLqR8nT5wY3kJ6hF1dZ4bA7eG0
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# AkiCapital
AKICAPITAL_URL=https://akipromotora.app/WebAutorizador/Login/AC.UI.LOGIN.aspx?FISession=7ed4824df157
AKICAPITAL_LOGIN=02622395230_901902
AKICAPITAL_SENHA=Efetiva26*

# GridSoftware / Roraima
GRID_URL=https://consignado.gridsoftware.com.br/grid/login.seam?
GRID_LOGIN=02622395230
GRID_SENHA=Manu@2025

# 2Captcha
TWOCAPTCHA_API_KEY=7e42177042c9c211507f578edf43c6fb
TWOCAPTCHA_TIMEOUT_S=120
TWOCAPTCHA_POLL_INTERVAL_S=5

# Sessoes Playwright
SESSION_DIR=/tmp/pw_sessions
ENVFILE
echo "      OK!"

# ── 6. Sobe os containers ─────────────────────────────────────────────────────
echo "[6/6] Subindo containers (pode demorar 5-10 min na primeira vez)..."
cd /opt/consulta-margem
docker compose up --build -d

echo ""
echo "============================================"
echo "  SISTEMA NO AR!"
echo ""
echo "  Acesse pelo navegador:"
echo "  http://95.111.248.228        (Interface)"
echo "  http://95.111.248.228:8000/docs  (API)"
echo "  http://95.111.248.228:5555   (Celery)"
echo "============================================"
echo ""
