from pathlib import Path

import pandas as pd
import pytest

from robo_boa_vista_excel import (
    detectar_coluna_identificador,
    montar_caminho_saida,
    preencher_resultados,
)


def test_detectar_coluna_identificador_prioriza_cpf():
    assert detectar_coluna_identificador(["Nome", "CPF", "matricula"]) == "CPF"


def test_detectar_coluna_identificador_aceita_matricula_com_acento():
    assert detectar_coluna_identificador(["Nome", "Matrícula"]) == "Matrícula"


def test_detectar_coluna_identificador_exige_coluna_valida():
    with pytest.raises(ValueError, match="cpf, matricula ou identificador"):
        detectar_coluna_identificador(["Nome", "Nascimento"])


def test_montar_caminho_saida_padrao():
    saida = montar_caminho_saida(Path("/tmp/entrada.xlsx"), None)
    assert saida == Path("/tmp/entrada_resultado.xlsx")


def test_preencher_resultados_cria_colunas_de_margem():
    df = pd.DataFrame({"cpf": ["12345678909"]})
    resultado = {
        0: {
            "status_consulta": "sucesso",
            "nome_titular": "SERVIDOR TESTE",
            "margem_disponivel": 100.50,
            "margem_cartao": 20.0,
            "margem_beneficio": 30.0,
        }
    }

    df_saida = preencher_resultados(df, "cpf", resultado)

    assert df_saida.at[0, "status_consulta"] == "sucesso"
    assert df_saida.at[0, "nome_titular"] == "SERVIDOR TESTE"
    assert df_saida.at[0, "margem_emprestimo"] == 100.50
    assert df_saida.at[0, "margem_cartao_consignado"] == 20.0
    assert df_saida.at[0, "margem_cartao_beneficio"] == 30.0
