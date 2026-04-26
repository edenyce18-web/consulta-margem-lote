#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  DEPLOY - ConsultaMargem v2.0"
echo "============================================"
echo ""

COMPOSE="docker compose -f /opt/consulta-margem/docker-compose.yml"
APP_DIR="/opt/consulta-margem"

# ── 1. Backup do banco ────────────────────────────────────────────────────────
echo "[1/6] Fazendo backup do banco de dados..."
BACKUP_FILE="$APP_DIR/backups/backup_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$APP_DIR/backups"
docker exec margem_db pg_dump -U postgres consulta_margem > "$BACKUP_FILE"
echo "      Backup salvo em: $BACKUP_FILE"

# ── 2. Atualiza código ────────────────────────────────────────────────────────
echo "[2/6] Atualizando código..."
cd "$APP_DIR"
git pull origin main
echo "      OK!"

# ── 3. Build das imagens ──────────────────────────────────────────────────────
echo "[3/6] Building containers..."
$COMPOSE build backend worker frontend
echo "      OK!"

# ── 4. Sobe os containers ─────────────────────────────────────────────────────
echo "[4/6] Subindo containers..."
$COMPOSE up -d
sleep 10
echo "      OK!"

# ── 4b. Garante senha correta do PostgreSQL (persiste ALTER USER no volume) ───
echo "[4b] Verificando senha do banco..."
docker exec margem_db psql -U postgres -c "ALTER USER postgres PASSWORD 'postgres';" 2>/dev/null \
  && echo "      Senha verificada/corrigida." \
  || echo "      AVISO: não foi possível verificar senha. Backend pode falhar."

# ── 5. Aplica migrations Alembic ──────────────────────────────────────────────
echo "[5/6] Aplicando migrations do banco..."
docker exec margem_backend sh -c "cd /app && alembic upgrade head"
echo "      OK!"

# ── 6. Health check ───────────────────────────────────────────────────────────
echo "[6/6] Verificando saúde da aplicação..."
sleep 5
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
if [ "$HTTP_STATUS" = "200" ]; then
    echo "      Health check OK (HTTP $HTTP_STATUS)"
else
    echo "      ERRO: Health check retornou HTTP $HTTP_STATUS"
    echo "      Verifique os logs: docker logs margem_backend --tail=50"
    exit 1
fi

echo ""
echo "============================================"
echo "  DEPLOY CONCLUIDO!"
echo ""
echo "  Interface:  http://$(curl -s ifconfig.me):8080"
echo "  API:        http://$(curl -s ifconfig.me):8000/docs"
echo "  Monitor:    http://$(curl -s ifconfig.me):5555"
echo "  Backup:     $BACKUP_FILE"
echo "============================================"
echo ""
