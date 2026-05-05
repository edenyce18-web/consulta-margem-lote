#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  SETUP - ConsultaMargem VPS v2.0"
echo "  Multi-usuário · AES-256 · JWT Refresh"
echo "============================================"
echo ""

# ── 1. Atualiza sistema ───────────────────────────────────────────────────────
echo "[1/7] Atualizando sistema..."
apt-get update -qq && apt-get upgrade -y -qq
echo "      OK!"

# ── 2. Instala Docker ─────────────────────────────────────────────────────────
echo "[2/7] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "      Docker instalado!"
else
    echo "      Docker já instalado, pulando."
fi

# ── 3. Instala Docker Compose plugin ─────────────────────────────────────────
echo "[3/7] Verificando Docker Compose..."
if ! docker compose version &> /dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi
docker compose version
echo "      OK!"

# ── 4. Clona o projeto ────────────────────────────────────────────────────────
echo "[4/7] Clonando projeto..."
if [ -d "/opt/consulta-margem" ]; then
    echo "      Pasta já existe, atualizando..."
    cd /opt/consulta-margem
    git pull
else
    git clone https://github.com/edenyce18-web/consulta-margem-lote.git /opt/consulta-margem
    cd /opt/consulta-margem
fi
echo "      OK!"

# ── 5. Gera chaves seguras automaticamente ────────────────────────────────────
echo "[5/7] Gerando chaves de segurança..."

# Instala python3 se necessário (para gerar chaves)
apt-get install -y -qq python3 > /dev/null 2>&1

# Gera SECRET_KEY (64 chars hex)
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Gera ENCRYPTION_KEY (32 bytes em base64 para AES-256)
ENCRYPTION_KEY=$(python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())")

echo "      Chaves geradas com sucesso!"

# ── 6. Cria arquivo .env com credenciais ──────────────────────────────────────
echo "[6/7] Configurando ambiente..."
cat > /opt/consulta-margem/backend/.env << ENVFILE
# ── Infraestrutura ────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:postgres@db:5432/consulta_margem
REDIS_URL=redis://redis:6379/0

# ── Autenticação JWT ──────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# ── Criptografia AES-256-GCM ──────────────────────────────────────────────────
ENCRYPTION_KEY=${ENCRYPTION_KEY}

# ── Rate Limiting ─────────────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=30

# ── AkiCapital (padrão — usuários adicionam credenciais pela interface) ────────
AKICAPITAL_URL=https://akipromotora.app/WebAutorizador/Login/AC.UI.LOGIN.aspx?FISession=7ed4824df157
AKICAPITAL_LOGIN=
AKICAPITAL_SENHA=

# ── GridSoftware / Roraima ────────────────────────────────────────────────────
GRID_URL=https://consignado.gridsoftware.com.br/grid/login.seam?
GRID_LOGIN=
GRID_SENHA=

# ── Prefeitura Boa Vista / RF1
BOAVISTA_URL=https://boavista.rf1consig.com.br/SGConsignataria/ConsigAcessoUsuarioLogar.aspx
BOAVISTA_LOGIN=
BOAVISTA_SENHA=
BOAVISTA_ORGAO=
BOAVISTA_CODIGO_SEGURANCA=

# ── 2Captcha ──────────────────────────────────────────────────────────────────
TWOCAPTCHA_API_KEY=7e42177042c9c211507f578edf43c6fb
TWOCAPTCHA_TIMEOUT_S=120
TWOCAPTCHA_POLL_INTERVAL_S=5

# ── Sessões Playwright ────────────────────────────────────────────────────────
SESSION_DIR=/tmp/pw_sessions
ENVFILE

# Exporta para docker-compose também
export SECRET_KEY
export ENCRYPTION_KEY

echo "      OK!"

# ── 7. Sobe os containers ─────────────────────────────────────────────────────
echo "[7/7] Subindo containers (pode demorar 5-10 min na primeira vez)..."
cd /opt/consulta-margem
SECRET_KEY=$SECRET_KEY ENCRYPTION_KEY=$ENCRYPTION_KEY docker compose up --build -d

echo ""
echo "============================================"
echo "  SISTEMA NO AR!"
echo ""
echo "  Acesse pelo navegador:"
echo "  http://95.111.248.228        (Interface Web)"
echo "  http://95.111.248.228:8000/docs  (API Swagger)"
echo "  http://95.111.248.228:5555   (Monitor Celery)"
echo ""
echo "  PRÓXIMOS PASSOS:"
echo "  1. Acesse a interface e crie sua conta"
echo "  2. Vá em 'Credenciais' e adicione seu"
echo "     login/senha do AkiCapital ou GridSoftware"
echo "  3. Faça upload de um CSV com CPFs"
echo "============================================"
echo ""
