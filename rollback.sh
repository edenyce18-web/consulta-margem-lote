#!/bin/bash
set -e

BACKUP_FILE=$1
APP_DIR="/opt/consulta-margem"
COMPOSE="docker compose -f $APP_DIR/docker-compose.yml"

echo ""
echo "============================================"
echo "  ROLLBACK - ConsultaMargem"
echo "============================================"
echo ""

if [ -z "$BACKUP_FILE" ]; then
    echo "Uso: ./rollback.sh <arquivo_backup.sql>"
    echo ""
    echo "Backups disponíveis:"
    ls -lt "$APP_DIR/backups/"*.sql 2>/dev/null | head -10 || echo "Nenhum backup encontrado."
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERRO: Arquivo '$BACKUP_FILE' não encontrado."
    exit 1
fi

echo "Backup a restaurar: $BACKUP_FILE"
echo ""
read -p "Tem certeza? Isso vai APAGAR os dados atuais do banco. (s/N) " confirm
if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
    echo "Rollback cancelado."
    exit 0
fi

# ── 1. Para os containers ─────────────────────────────────────────────────────
echo "[1/4] Parando containers..."
$COMPOSE stop backend worker flower frontend
echo "      OK!"

# ── 2. Restaura banco ─────────────────────────────────────────────────────────
echo "[2/4] Restaurando banco de dados..."
docker exec -i margem_db psql -U postgres -c "DROP DATABASE IF EXISTS consulta_margem;" postgres
docker exec -i margem_db psql -U postgres -c "CREATE DATABASE consulta_margem;" postgres
docker exec -i margem_db psql -U postgres consulta_margem < "$BACKUP_FILE"
echo "      Banco restaurado!"

# ── 3. Volta código ───────────────────────────────────────────────────────────
echo "[3/4] Voltando código para commit anterior..."
cd "$APP_DIR"
git log --oneline -5
echo ""
read -p "Digite o hash do commit para voltar (ou Enter para cancelar): " commit_hash
if [ -n "$commit_hash" ]; then
    git checkout "$commit_hash" -- .
    echo "      Código voltado para $commit_hash"
fi

# ── 4. Sobe containers ────────────────────────────────────────────────────────
echo "[4/4] Subindo containers..."
$COMPOSE up -d
sleep 10

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
echo "      Health check: HTTP $HTTP_STATUS"

echo ""
echo "============================================"
echo "  ROLLBACK CONCLUIDO!"
echo "============================================"
echo ""
