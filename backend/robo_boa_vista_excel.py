"""
Robô local Boa Vista/RF1Consig para consulta em lote por Excel ou CSV.

Exemplo:
    python backend/robo_boa_vista_excel.py --arquivo entrada.xlsx --login 00000000000 --senha MINHA_SENHA --twocaptcha-api-key SUA_CHAVE

A planilha precisa ter uma coluna chamada "cpf", "matricula" ou "identificador".
O arquivo de saída recebe as colunas de margens de empréstimo, cartão consignado
(cartão de crédito) e cartão benefício.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterable

import pandas as pd

# Permite executar o arquivo diretamente a partir da raiz do projeto.
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.scraper.browser_pool import BrowserLote
from app.scraper.manager import AdapterManager
import app.scraper  # noqa: F401  # importa adaptadores e registra a chave "bv"

logger = logging.getLogger("robo_boa_vista_excel")

URL_CONSULTA_BOA_VISTA = (
    "https://boavista.rf1consig.com.br/SGConsignataria/GESTOR/CADPessoaListar.aspx"
)
COLUNAS_IDENTIFICADOR = ("cpf", "matricula", "matrícula", "identificador")
COLUNAS_RESULTADO = {
    "status_consulta": "status_consulta",
    "mensagem_erro": "mensagem_erro",
    "nome_titular": "nome_titular",
    "orgao": "orgao",
    "matricula_resultado": "matricula",
    "tipo_vinculo": "tipo_vinculo",
    "margem_emprestimo": "margem_disponivel",
    "margem_cartao_consignado": "margem_cartao",
    "margem_cartao_beneficio": "margem_beneficio",
    "emprestimo_situacao": "emprestimo_situacao",
    "cartao_consignado_situacao": "cartao_credito_situacao",
    "cartao_beneficio_situacao": "cartao_beneficio_situacao",
    "banco": "banco",
}


def configurar_logs(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def configurar_twocaptcha(api_key: str | None) -> None:
    """Garante que o robô rode 100% automático em portais com CAPTCHA."""
    chave = (
        api_key
        or os.environ.get("TWOCAPTCHA_API_KEY")
        or settings.TWOCAPTCHA_API_KEY
        or ""
    ).strip()
    if not chave:
        raise ValueError(
            "O RF1Consig usa código de segurança/CAPTCHA. Para o robô consultar sozinho, "
            "informe uma chave 2Captcha com --twocaptcha-api-key SUA_CHAVE ou configure "
            "TWOCAPTCHA_API_KEY no backend/.env/ambiente."
        )
    os.environ["TWOCAPTCHA_API_KEY"] = chave
    settings.TWOCAPTCHA_API_KEY = chave


def detectar_coluna_identificador(colunas: Iterable[str]) -> str:
    mapa = {str(col).strip().lower(): str(col) for col in colunas}
    for nome in COLUNAS_IDENTIFICADOR:
        if nome in mapa:
            return mapa[nome]
    raise ValueError(
        "A planilha precisa ter uma coluna chamada cpf, matricula ou identificador."
    )


def ler_planilha(caminho: Path) -> tuple[pd.DataFrame, str]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    if caminho.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(caminho, dtype=str)
    elif caminho.suffix.lower() == ".csv":
        df = pd.read_csv(caminho, dtype=str, sep=None, engine="python")
    else:
        raise ValueError("Use um arquivo .xlsx, .xlsm, .xls ou .csv.")

    coluna = detectar_coluna_identificador(df.columns)
    df[coluna] = df[coluna].fillna("").astype(str).str.strip()
    df = df[df[coluna] != ""].copy()
    if df.empty:
        raise ValueError("Nenhum CPF ou matrícula preenchido foi encontrado na planilha.")
    return df, coluna


def montar_caminho_saida(entrada: Path, saida: str | None) -> Path:
    if saida:
        return Path(saida).expanduser().resolve()
    return entrada.with_name(f"{entrada.stem}_resultado{entrada.suffix}")


def salvar_resultado(df: pd.DataFrame, saida: Path) -> None:
    saida.parent.mkdir(parents=True, exist_ok=True)
    if saida.suffix.lower() == ".csv":
        df.to_csv(saida, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(saida, index=False)


def preencher_resultados(
    df: pd.DataFrame,
    coluna_identificador: str,
    resultados: dict[int, dict],
) -> pd.DataFrame:
    df_saida = df.copy()
    for coluna in COLUNAS_RESULTADO:
        if coluna not in df_saida.columns:
            df_saida[coluna] = ""

    for idx, resultado in resultados.items():
        for coluna_saida, chave_resultado in COLUNAS_RESULTADO.items():
            valor = resultado.get(chave_resultado)
            df_saida.at[idx, coluna_saida] = "" if valor is None else valor

    return df_saida


def consultar_lote(
    identificadores: list[tuple[int, str]],
    login: str,
    senha: str,
    url: str,
) -> dict[int, dict]:
    credencial = {
        "id": "robo-local-boa-vista",
        "login": login,
        "senha": senha,
        "url": url,
    }
    adapter = AdapterManager.obter("bv", credencial=credencial, usuario_id="robo-local")
    resultados: dict[int, dict] = {}

    with BrowserLote(adapter, cpfs_total=len(identificadores)) as browser_lote:
        for posicao, (idx, identificador) in enumerate(identificadores, start=1):
            inicio = time.time()
            logger.info("[%d/%d] Consultando %s", posicao, len(identificadores), identificador)
            resultado = browser_lote.consultar(identificador)
            resultados[idx] = resultado
            logger.info(
                "[%d/%d] %s → %s em %.1fs",
                posicao,
                len(identificadores),
                identificador,
                resultado.get("status_consulta"),
                time.time() - inicio,
            )
    return resultados


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Consulta margens Boa Vista/RF1Consig em lote e grava resultado no Excel."
    )
    parser.add_argument("--arquivo", required=True, help="Caminho da planilha .xlsx/.csv de entrada.")
    parser.add_argument("--saida", help="Caminho do arquivo de saída. Padrão: *_resultado.xlsx/csv.")
    parser.add_argument("--login", required=True, help="CPF/login do usuário no portal RF1Consig.")
    parser.add_argument("--senha", required=True, help="Senha do portal RF1Consig.")
    parser.add_argument(
        "--twocaptcha-api-key",
        help=(
            "Chave 2Captcha para resolver automaticamente o código de segurança do RF1Consig. "
            "Também pode ser informada pela variável TWOCAPTCHA_API_KEY ou backend/.env."
        ),
    )
    parser.add_argument(
        "--url",
        default=URL_CONSULTA_BOA_VISTA,
        help="URL inicial do portal. Padrão: página CADPessoaListar da Prefeitura de Boa Vista.",
    )
    parser.add_argument("--verbose", action="store_true", help="Mostra logs detalhados.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configurar_logs(args.verbose)

    configurar_twocaptcha(args.twocaptcha_api_key)

    entrada = Path(args.arquivo).expanduser().resolve()
    saida = montar_caminho_saida(entrada, args.saida)

    df, coluna_identificador = ler_planilha(entrada)
    coluna_normalizada = coluna_identificador.strip().lower()
    forcar_matricula = coluna_normalizada in ("matricula", "matrícula")
    identificadores = []
    for idx, valor in df[coluna_identificador].items():
        identificador = str(valor).strip()
        if forcar_matricula:
            identificador = f"matricula:{identificador}"
        identificadores.append((idx, identificador))

    logger.info("Arquivo: %s", entrada)
    logger.info("Saída: %s", saida)
    logger.info("Coluna usada: %s | total: %d", coluna_identificador, len(identificadores))

    resultados = consultar_lote(identificadores, args.login, args.senha, args.url)
    df_saida = preencher_resultados(df, coluna_identificador, resultados)
    salvar_resultado(df_saida, saida)

    logger.info("Concluído. Resultado salvo em: %s", saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
