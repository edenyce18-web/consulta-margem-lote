"""
scraper/akicapital_adapter.py
──────────────────────────────
Adaptador para o portal AkiCapital (WebAutorizador ASP.NET).

URL:    https://akipromotora.app/WebAutorizador/Login/AC.UI.LOGIN.aspx?FISession=7ed4824df157
Login:  02622395230_901902 / Efetiva26*

Estrutura da página de resultado (conforme tela real):
  ┌──────────────────────────────────────────────────────┐
  │ CPF: 46733671700   Nome: BARBARA RODRIGUES MAGALHAES │
  │ Tipo Vínculo: Servidor  Órgão: 25000-MIN.SAUDE  Mat. │
  ├──────────────────────────────────────────────────────┤
  │ EMPRÉSTIMO BANCOS PRIVADOS                           │
  │   Empréstimo    │ Não Autorizado                     │
  │   Portabilidade │ Não Autorizado                     │
  ├──────────────────────────────────────────────────────┤
  │ CARTÃO DE CRÉDITO                                    │
  │   Cartão de Crédito │ Não Autorizado                 │
  ├──────────────────────────────────────────────────────┤
  │ CARTÃO BENEFÍCIO    Margem Consignável: R$ 39,75     │
  │   Cartão de Benefício │ Autorizado                   │
  └──────────────────────────────────────────────────────┘

Campos extraídos:
  - nome_titular
  - tipo_vinculo, orgao, matricula
  - emprestimo_situacao      (Autorizado / Não Autorizado)
  - portabilidade_situacao   (Autorizado / Não Autorizado)
  - cartao_credito_situacao  (Autorizado / Não Autorizado)
  - cartao_beneficio_situacao (Autorizado / Não Autorizado)
  - margem_beneficio         (float — só presente se Autorizado)

  status_consulta:
    "sucesso"    → pelo menos um produto Autorizado
    "sem_margem" → todos Não Autorizado (cliente existe mas sem autorização)
    "erro"       → falha técnica
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.config import settings
from app.scraper.base_adapter import (
    BaseScraperAdapter,
    TIMEOUT_NAV, TIMEOUT_EL, TIMEOUT_CONS,
)
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    formatar_cpf, pausa_humana, digitar_lento,
    parse_moeda, resultado_erro, resultado_sem_margem,
)

logger = logging.getLogger(__name__)


@AdapterManager.registrar("aki")
class AkiCapitalAdapter(BaseScraperAdapter):
    """
    Adaptador para o portal AkiCapital / WebAutorizador ASP.NET.

    Extrai os campos de autorização de cada produto consignado:
    Empréstimo, Portabilidade, Cartão de Crédito e Cartão Benefício
    (com Margem Consignável quando disponível).
    """

    NOME_BANCO   = "AkiCapital"
    CHAVE_SESSAO = "akicapital"
    URL_LOGIN    = settings.AKICAPITAL_URL

    # ── Seletores — tela de login ─────────────────────────────────────────────
    SEL_USUARIO = "#EUsuario_CAMPO"
    SEL_SENHA   = "#ESenha_CAMPO"
    SEL_ENTRAR  = "#lnkEntrar"

    # ── Seletores — área logada ───────────────────────────────────────────────
    SEL_AREA_LOGADA = [
        "#lnkSair",
        "#lnkLogout",
        ".menu-principal",
        "#divMenuTopo",
        "[id*='LogOff']",
        "[id*='Logout']",
    ]

    # ── Seletores — campo de CPF na consulta ─────────────────────────────────
    SEL_CAMPO_CPF = [
        "#ECPF_CAMPO",
        "#txtCPF",
        "input[id*='CPF']",
        "input[name*='cpf']",
        "input[placeholder*='CPF']",
    ]

    # ── Seletores — botão consultar ───────────────────────────────────────────
    SEL_BTN_CONSULTAR = [
        "#lnkConsultar",
        "#btnConsultar",
        "#lnkPesquisar",
        "input[type='submit'][value*='Consultar']",
        "a[id*='Consultar']",
        "button:has-text('Consultar')",
    ]

    # ── Seletores — presença de resultado ────────────────────────────────────
    SEL_RESULTADO = [
        "td:has-text('EMPRÉSTIMO BANCOS PRIVADOS')",
        "td:has-text('CARTÃO DE CRÉDITO')",
        "td:has-text('CARTÃO BENEFÍCIO')",
        "td:has-text('Empréstimo Bancos Privados')",
        "#GridResultados",
        "#tblMargem",
        "#divResultado",
        "table[id*='Grid']",
    ]

    # ── Verificação de sessão ─────────────────────────────────────────────────

    def _esta_logado(self, page) -> bool:
        url = page.url.lower()
        if "login" in url:
            return False
        return self._primeiro_seletor(page, self.SEL_AREA_LOGADA) is not None

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _fazer_login(self, page) -> None:
        logger.info("[AkiCapital] Navegando para tela de login.")
        page.goto(self.URL_LOGIN, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_EL)

        page.click(self.SEL_USUARIO)
        digitar_lento(page, self.SEL_USUARIO, settings.AKICAPITAL_LOGIN)
        pausa_humana(0.5, 1.0)

        page.click(self.SEL_SENHA)
        digitar_lento(page, self.SEL_SENHA, settings.AKICAPITAL_SENHA)
        pausa_humana(0.5, 1.2)

        page.click(self.SEL_ENTRAR)
        logger.info("[AkiCapital] Aguardando redirecionamento pós-login...")

        try:
            page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('login')",
                timeout=15_000,
            )
        except Exception:
            sel = self._primeiro_seletor(page, self.SEL_AREA_LOGADA)
            if not sel:
                erro_txt = self._texto_seletor(page, [
                    ".MensagemErro", "#lblErro", ".alert-danger",
                    "[class*='erro']", "[class*='error']",
                ])
                raise RuntimeError(
                    f"Login falhou. Mensagem do portal: {erro_txt or 'sem detalhes'}"
                )

        pausa_humana(1.0, 2.0)
        logger.info("[AkiCapital] Login concluído. URL atual: %s", page.url)

    # ── Navegação para tela de consulta ──────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        sel_menu = self._primeiro_seletor(page, [
            "a:has-text('Consulta de Margem')",
            "a:has-text('Margem Consignada')",
            "a:has-text('Consultar Margem')",
            "a:has-text('Consultar')",
            "#mnuConsultaMargem",
            "a[href*='ConsultaMargem']",
            "a[href*='Margem']",
        ])

        if sel_menu:
            page.click(sel_menu)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_NAV)
            pausa_humana(1.0, 2.0)
            logger.info("[AkiCapital] Navegou para consulta via menu.")
            return

        base = re.sub(r"/Login/.*", "", self.URL_LOGIN.split("?")[0])
        url_consulta = f"{base}/Consulta/ConsultaMargem.aspx"
        logger.warning("[AkiCapital] Menu não encontrado — tentando URL: %s", url_consulta)
        page.goto(url_consulta, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

    # ── Extração completa ─────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        self._navegar_para_consulta(page)

        # ── Insere CPF ────────────────────────────────────────────────────────
        campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF)
        if not campo_cpf:
            return resultado_erro(
                "Campo CPF não encontrado na página de consulta.",
                cpf, self.NOME_BANCO,
            )

        # Limpa campo e digita o CPF formatado
        page.fill(campo_cpf, "")
        digitar_lento(page, campo_cpf, formatar_cpf(cpf))
        pausa_humana(0.5, 1.0)

        # ── Clica em consultar ────────────────────────────────────────────────
        btn = self._primeiro_seletor(page, self.SEL_BTN_CONSULTAR)
        if btn:
            page.click(btn)
        else:
            page.keyboard.press("Enter")

        # ── Aguarda resultado ─────────────────────────────────────────────────
        try:
            page.wait_for_selector(
                ", ".join(self.SEL_RESULTADO),
                timeout=TIMEOUT_CONS,
            )
        except Exception:
            conteudo = page.content().lower()
            if any(x in conteudo for x in [
                "não encontrado", "sem margem", "não possui",
                "cpf não", "nenhum registro",
            ]):
                return resultado_sem_margem(cpf, self.NOME_BANCO)
            return resultado_erro(
                "Timeout aguardando resultado de consulta.", cpf, self.NOME_BANCO
            )

        pausa_humana(0.5, 1.0)

        # ── Extrai dados do servidor ──────────────────────────────────────────
        nome_txt     = self._extrair_celula_apos(page, "Nome")
        orgao_txt    = self._extrair_celula_apos(page, "Órgão")
        vinculo_txt  = self._extrair_celula_apos(page, "Tipo Vínculo")
        matricula_txt = self._extrair_celula_apos(page, "Matrícula")

        # ── Extrai situação de cada produto ───────────────────────────────────
        emp_sit = self._situacao_produto(page, "Empréstimo")
        cc_sit  = self._situacao_produto(page, "Cartão de Crédito")
        cb_sit  = self._situacao_produto(page, "Cartão de Benefício")

        # ── Margem Consignável do Cartão Benefício ────────────────────────────
        margem_beneficio = self._extrair_margem_beneficio(page)

        # ── Determina status geral ────────────────────────────────────────────
        autorizados = [s for s in [emp_sit, cc_sit, cb_sit]
                       if s and "autorizado" in s.lower() and "não" not in s.lower()]
        status = "sucesso" if (autorizados or margem_beneficio) else "sem_margem"

        logger.info(
            "[AkiCapital] CPF %s | Nome: %s | Emp: %s | CC: %s | CB: %s | MargBen: R$%s",
            cpf, nome_txt, emp_sit, cc_sit, cb_sit, margem_beneficio,
        )

        return {
            "cpf":             cpf,
            "status_consulta": status,
            "mensagem_erro":   None,

            # Dados do servidor
            "nome_titular": nome_txt,
            "orgao":        orgao_txt,
            "tipo_vinculo": vinculo_txt,
            "matricula":    matricula_txt,

            # Margens em R$ — Aki só expõe o valor do Cartão Benefício
            "margem_disponivel": None,
            "margem_cartao":     None,
            "margem_beneficio":  margem_beneficio,

            # Situação de autorização por produto
            "emprestimo_situacao":       emp_sit,
            "cartao_credito_situacao":   cc_sit,
            "cartao_beneficio_situacao": cb_sit,

            "banco": self.NOME_BANCO,
            "dados_brutos": json.dumps({
                "emprestimo_situacao":       emp_sit,
                "cartao_credito_situacao":   cc_sit,
                "cartao_beneficio_situacao": cb_sit,
                "margem_beneficio":          str(margem_beneficio),
                "url_consulta":              page.url,
            }, ensure_ascii=False),
        }

    # ── Helpers de extração ───────────────────────────────────────────────────

    def _extrair_celula_apos(self, page, rotulo: str) -> Optional[str]:
        """
        Localiza uma célula de tabela com o rótulo exato e retorna
        o texto da célula adjacente (irmã imediata).

        Funciona com estruturas:
          <td>Rótulo</td><td>Valor</td>
          <td>Rótulo:</td><td>Valor</td>
        """
        try:
            cells = page.locator("td").all()
            for i, cell in enumerate(cells):
                txt = (cell.text_content() or "").strip().rstrip(":")
                if txt.lower() == rotulo.lower() and i + 1 < len(cells):
                    valor = (cells[i + 1].text_content() or "").strip()
                    if valor:
                        return valor
        except Exception:
            pass
        return None

    def _situacao_produto(self, page, nome_produto: str) -> Optional[str]:
        """
        Localiza a linha de um produto na tabela de autorizações e retorna
        a coluna "Situação" (Autorizado / Não Autorizado).

        Estrutura esperada:
          <tr><td>Empréstimo</td><td>Autorizado</td></tr>
          <tr><td>Portabilidade</td><td>Não Autorizado</td></tr>
        """
        try:
            rows = page.locator("tr").all()
            for row in rows:
                cells = row.locator("td").all()
                if len(cells) >= 2:
                    label = (cells[0].text_content() or "").strip()
                    if label.lower() == nome_produto.lower():
                        situacao = (cells[1].text_content() or "").strip()
                        return situacao if situacao else None
        except Exception:
            pass
        return None

    def _extrair_margem_beneficio(self, page) -> Optional[float]:
        """
        Localiza o texto 'Margem Consignável: R$ XX,XX' na seção
        CARTÃO BENEFÍCIO e extrai o valor numérico.

        Exemplos de texto encontrado na página:
          "CARTÃO BENEFÍCIO   Margem Consignável: R$ 39,75"
          "Margem Consignável: R$ 39,75"
        """
        try:
            # Tenta seletor direto com texto
            for sel in [
                "td:has-text('Margem Consignável')",
                "th:has-text('Margem Consignável')",
                "*:has-text('Margem Consignável')",
            ]:
                loc = page.locator(sel)
                if loc.count() > 0:
                    texto = loc.first.text_content() or ""
                    match = re.search(
                        r"Margem\s+Consign[aá]vel\s*:\s*R\$\s*([\d.,]+)",
                        texto, re.IGNORECASE
                    )
                    if match:
                        return parse_moeda(match.group(1))

            # Fallback: varre todo o HTML em busca do padrão
            html = page.content()
            match = re.search(
                r"Margem\s+Consign[aá]vel\s*:\s*R\$\s*([\d.,]+)",
                html, re.IGNORECASE
            )
            if match:
                return parse_moeda(match.group(1))

        except Exception:
            pass
        return None
