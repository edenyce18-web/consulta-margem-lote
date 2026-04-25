"""
scraper/utils.py
────────────────
Utilitários compartilhados entre todos os adaptadores.
"""

from __future__ import annotations

import re
import time
import random
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── CPF ───────────────────────────────────────────────────────────────────────

def limpar_cpf(cpf: str) -> str:
    """Remove qualquer caractere não-numérico do CPF."""
    return re.sub(r"\D", "", cpf)


def formatar_cpf(cpf: str) -> str:
    """Retorna CPF no formato 000.000.000-00."""
    c = limpar_cpf(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else cpf


def validar_cpf(cpf: str) -> bool:
    """Valida CPF com algoritmo de dígitos verificadores."""
    cpf = limpar_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


# ── Resultado padrão ──────────────────────────────────────────────────────────

def resultado_erro(mensagem: str, cpf: str, banco: str = "") -> dict:
    """Retorna dict de erro no formato esperado pelo banco de dados."""
    return {
        "cpf": cpf,
        "status_consulta": "erro",
        "mensagem_erro": mensagem,
        "margem_disponivel": None,
        "margem_cartao": None,
        "margem_beneficio": None,
        "nome_titular": None,
        "banco": banco or None,
        "orgao": None,
        "dados_brutos": None,
    }


def resultado_sem_margem(cpf: str, banco: str = "") -> dict:
    return {
        **resultado_erro("Sem margem disponível", cpf, banco),
        "status_consulta": "sem_margem",
    }


def resultado_cpf_invalido(cpf: str, banco: str = "") -> dict:
    return {
        **resultado_erro("CPF inválido", cpf, banco),
        "status_consulta": "cpf_invalido",
    }


# ── Moeda ─────────────────────────────────────────────────────────────────────

def parse_moeda(texto: Optional[str]) -> Optional[float]:
    """Converte 'R$ 1.234,56' → 1234.56. Retorna None se inválido."""
    if not texto:
        return None
    try:
        limpo = re.sub(r"[R$\s\xa0]", "", str(texto)).replace(".", "").replace(",", ".")
        return float(limpo)
    except (ValueError, AttributeError):
        return None


# ── Timing humano ─────────────────────────────────────────────────────────────

def pausa_humana(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """Aguarda um intervalo aleatório para simular comportamento humano."""
    time.sleep(random.uniform(min_s, max_s))


def digitar_lento(page, seletor: str, texto: str) -> None:
    """Preenche um campo com digitação simulada (delay por tecla)."""
    page.fill(seletor, "")
    page.type(seletor, texto, delay=random.randint(60, 130))


# ── Debug ─────────────────────────────────────────────────────────────────────

def salvar_screenshot(page, prefixo: str, session_dir: Path) -> None:
    """Salva screenshot em SESSION_DIR para diagnóstico de erros."""
    try:
        caminho = session_dir / f"{prefixo}_{int(time.time())}.png"
        page.screenshot(path=str(caminho), full_page=True)
        logger.warning("Screenshot salvo: %s", caminho)
    except Exception as exc:
        logger.debug("Falha ao salvar screenshot: %s", exc)
