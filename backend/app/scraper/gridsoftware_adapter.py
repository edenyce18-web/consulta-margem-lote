"""
scraper/gridsoftware_adapter.py
─────────────────────────────────
Adaptador para o portal GridSoftware SIGAC-Web (Roraima).

Suporte a credenciais dinâmicas por usuário:
    adapter = GridSoftwareAdapter(credencial={"login": "...", "senha": "..."})
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from app.config import settings
from app.scraper.base_adapter import (
    BaseScraperAdapter,
    TIMEOUT_NAV, TIMEOUT_EL, TIMEOUT_CONS,
)
from app.scraper.captcha import TwoCaptchaSolver
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    formatar_cpf, pausa_humana, digitar_lento,
    parse_moeda, resultado_erro, resultado_sem_margem,
)

logger = logging.getLogger(__name__)


@AdapterManager.registrar("grid")
class GridSoftwareAdapter(BaseScraperAdapter):
    """Adaptador para o portal GridSoftware SIGAC-Web (Roraima)."""

    NOME_BANCO   = "GridSoftware / Roraima"
    CHAVE_SESSAO = "grid_roraima"

    _URL_LOGIN_DEFAULT = settings.GRID_URL

    @property
    def _url_base(self) -> str:
        url = self.URL_LOGIN
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/grid/"

    # ── Seletores ─────────────────────────────────────────────────────────────
    SEL_BTN_CONSIGNATARIA = "#j_idt15\\:btnConsignataria"
    SEL_USUARIO           = "#username"
    SEL_SENHA             = "#password"
    SEL_SUBMIT            = "#submit"
    SEL_RECAPTCHA         = ".g-recaptcha"

    SEL_AREA_LOGADA = [
        "#j_idt_logout", "[id*='sair']", "[id*='logout']",
        ".ui-menubar", "#formPrincipal",
    ]
    SEL_CAMPO_CPF = [
        "#formConsulta\\:cpf", "#formConsulta\\:inputCpf",
        "input[id*='cpf']", "input[name*='cpf']", "input[placeholder*='CPF']",
    ]
    SEL_BTN_CONSULTAR = [
        "#formConsulta\\:btnConsultar", "button:has-text('Consultar')",
        "input[value='Consultar']", "a:has-text('Consultar')",
    ]
    SEL_RESULTADO = [
        "#formResultado", ".ui-datatable", "#tblMargem",
        ".resultado-margem", "#panelResultado",
    ]
    SEL_ABA_EMPRESTIMO = [
        "a:has-text('Margem de Empréstimo')", "a:has-text('Empréstimo')",
        ".ui-tabview-nav li:first-child a", "#tabEmprestimo",
    ]
    SEL_ABA_CARTAO = [
        "a:has-text('Margem de Cartão')", "a:has-text('Cartão')",
        ".ui-tabview-nav li:nth-child(2) a", "#tabCartao",
    ]
    SEL_VALOR_EMPRESTIMO = [
        "#formResultado\\:margemEmprestimo", "#formResultado\\:vlrMargem",
        "td:has-text('Margem Disponível') + td", "td:has-text('Margem de Empréstimo') + td",
        ".margem-emprestimo",
    ]
    SEL_VALOR_CARTAO = [
        "#formResultado\\:margemCartao", "#formResultado\\:vlrCartao",
        "td:has-text('Margem de Cartão') + td", "td:has-text('Cartão de Crédito') + td",
        ".margem-cartao",
    ]

    def __init__(self, credencial: Optional[dict] = None):
        super().__init__(credencial)
        self.URL_LOGIN = (
            (credencial or {}).get("url")
            or self._URL_LOGIN_DEFAULT
        )

    @property
    def _login(self) -> str:
        return self._credencial.get("login") or settings.GRID_LOGIN

    @property
    def _senha(self) -> str:
        return self._credencial.get("senha") or settings.GRID_SENHA

    # ── Verificação de sessão ─────────────────────────────────────────────────

    def _esta_logado(self, page) -> bool:
        if "login" in page.url.lower():
            return False
        return self._primeiro_seletor(page, self.SEL_AREA_LOGADA) is not None

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _fazer_login(self, page) -> None:
        logger.info("[GridSoftware] Navegando para tela de login.")
        page.goto(self.URL_LOGIN, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.5)

        self._clicar_btn_consignataria(page)

        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_EL)

        page.click(self.SEL_USUARIO)
        digitar_lento(page, self.SEL_USUARIO, self._login)
        pausa_humana(0.5, 1.0)

        page.click(self.SEL_SENHA)
        digitar_lento(page, self.SEL_SENHA, self._senha)
        pausa_humana(0.5, 1.0)

        self._resolver_captcha_se_presente(page)

        page.click(self.SEL_SUBMIT)
        logger.info("[GridSoftware] Formulário submetido — aguardando redirecionamento.")

        try:
            page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('login')",
                timeout=20_000,
            )
        except Exception:
            erro_txt = self._texto_seletor(page, [
                ".ui-messages-error", ".ui-message-error-detail",
                "#mensagemErro", ".login-error", "[class*='erro']",
            ])
            if erro_txt:
                raise RuntimeError(f"Login GridSoftware falhou: {erro_txt}")
            page.wait_for_load_state("networkidle", timeout=15_000)

        pausa_humana(1.0, 2.0)
        logger.info("[GridSoftware] Login concluído. URL: %s", page.url)

    def _clicar_btn_consignataria(self, page) -> None:
        seletores = [
            self.SEL_BTN_CONSIGNATARIA,
            "button:has-text('Consignatária')",
            "a:has-text('Consignatária')",
            "input[value*='Consignatária']",
        ]
        sel = self._primeiro_seletor(page, seletores)
        if sel:
            page.click(sel)
            pausa_humana(1.0, 2.0)
        else:
            logger.warning("[GridSoftware] Botão 'Consignatária' não encontrado.")

    def _resolver_captcha_se_presente(self, page) -> None:
        solver = TwoCaptchaSolver()
        sitekey = solver.extrair_sitekey(page)
        if not sitekey:
            return
        logger.info("[GridSoftware] reCAPTCHA detectado. Resolvendo via 2Captcha...")
        token = solver.resolver(sitekey=sitekey, page_url=page.url)
        solver.injetar_token(page, token)
        pausa_humana(1.0, 2.0)

    # ── Navegação para consulta ───────────────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        sel_menu = self._primeiro_seletor(page, [
            "a:has-text('Consulta de Margem')",
            "a:has-text('Margem Consignada')",
            "a:has-text('Consultar')",
            "a[href*='consultaMargem']",
            "a[href*='margem']",
            ".ui-menuitem:has-text('Margem') a",
        ])

        if sel_menu:
            page.click(sel_menu)
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_NAV)
            pausa_humana(1.0, 2.0)
            return

        url_consulta = urljoin(self._url_base, "margem/consultaMargem.seam")
        logger.warning("[GridSoftware] Menu não localizado — tentando URL direta: %s", url_consulta)
        page.goto(url_consulta, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

    # ── Extração ──────────────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        self._navegar_para_consulta(page)

        campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF)
        if not campo_cpf:
            return resultado_erro(
                "Campo CPF não encontrado na tela de consulta.", cpf, self.NOME_BANCO
            )

        digitar_lento(page, campo_cpf, formatar_cpf(cpf))
        pausa_humana(0.5, 1.0)

        btn = self._primeiro_seletor(page, self.SEL_BTN_CONSULTAR)
        if btn:
            page.click(btn)
        else:
            page.keyboard.press("Enter")

        try:
            page.wait_for_selector(
                ", ".join(self.SEL_RESULTADO),
                timeout=TIMEOUT_CONS,
            )
        except Exception:
            conteudo = page.content().lower()
            if any(x in conteudo for x in [
                "não encontrado", "sem margem", "não possui", "nenhum registro",
            ]):
                return resultado_sem_margem(cpf, self.NOME_BANCO)
            return resultado_erro(
                "Resultado não carregou no tempo esperado.", cpf, self.NOME_BANCO
            )

        pausa_humana(0.3, 0.8)

        nome_txt = self._texto_seletor(page, [
            "#formResultado\\:nome", "#formResultado\\:nomeServidor",
            "td:has-text('Nome') + td", ".nome-servidor",
        ])
        orgao_txt = self._texto_seletor(page, [
            "#formResultado\\:orgao", "#formResultado\\:nomeOrgao",
            "td:has-text('Órgão') + td", ".orgao-servidor",
        ])

        margem_emprestimo = self._ler_aba(
            page, self.SEL_ABA_EMPRESTIMO, self.SEL_VALOR_EMPRESTIMO, "Margem de Empréstimo"
        )
        margem_cartao = self._ler_aba(
            page, self.SEL_ABA_CARTAO, self.SEL_VALOR_CARTAO, "Margem de Cartão"
        )

        status = (
            "sucesso"
            if (margem_emprestimo is not None or margem_cartao is not None)
            else "sem_margem"
        )

        return {
            "cpf":               cpf,
            "status_consulta":   status,
            "mensagem_erro":     None,
            "nome_titular":      nome_txt,
            "margem_disponivel": margem_emprestimo,
            "margem_cartao":     margem_cartao,
            "margem_beneficio":  None,
            "banco":             self.NOME_BANCO,
            "orgao":             orgao_txt,
            "dados_brutos":      json.dumps({
                "margem_emprestimo": str(margem_emprestimo),
                "margem_cartao":     str(margem_cartao),
                "url_consulta":      page.url,
            }, ensure_ascii=False),
        }

    def _ler_aba(self, page, seletores_aba, seletores_valor, nome_aba) -> Optional[float]:
        sel_aba = self._primeiro_seletor(page, seletores_aba)
        if sel_aba:
            try:
                page.click(sel_aba)
                pausa_humana(0.5, 1.0)
            except Exception as exc:
                logger.warning("[GridSoftware] Não foi possível clicar na aba '%s': %s", nome_aba, exc)

        texto = self._texto_seletor(page, seletores_valor)
        return parse_moeda(texto)
