"""
scraper/gridsoftware_adapter.py
─────────────────────────────────
Adaptador para o portal GridSoftware SIGAC-Web (Roraima).

URL:    https://consignado.gridsoftware.com.br/grid/login.seam?
Login:  02622395230 / Manu@2025  (perfil Consignatária)

Fluxo de login:
  1. GET → URL_LOGIN (página JSF / PrimeFaces)
  2. Clica em 'Consignatária' (#j_idt15:btnConsignataria) para
     selecionar o perfil correto de acesso
  3. Aguarda aparecer os campos #username e #password
  4. Preenche as credenciais com digitação simulada
  5. Extrai o sitekey do reCAPTCHA via TwoCaptchaSolver
  6. Submete à API do 2Captcha e aguarda token
  7. Injeta token no campo oculto g-recaptcha-response
  8. Clica #submit e aguarda redirecionamento para área logada

Fluxo de consulta:
  1. Navega para tela de consulta de margem
  2. Insere CPF formatado
  3. Lê a aba "Margem de Empréstimo" → margem_disponivel
  4. Lê a aba "Margem de Cartão"     → margem_cartao
  5. Consolida os dois valores no resultado final

Sessão persistente:
  - Salva estado em /tmp/pw_sessions/grid_roraima.json
  - reCAPTCHA resolvido apenas no primeiro login do worker

Configuração (.env):
  GRID_URL           → URL de login do GridSoftware
  GRID_LOGIN         → CPF do operador (só dígitos)
  GRID_SENHA         → Senha
  TWOCAPTCHA_API_KEY → Chave 2captcha.com
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
    """
    Adaptador para o portal GridSoftware SIGAC-Web (Roraima).

    Desafios especiais:
      - JSF / PrimeFaces (seletores com ':' que precisam de escape CSS)
      - reCAPTCHA v2 resolvido via 2Captcha antes do submit
      - Duas abas de margem (empréstimo + cartão) que precisam
        ser lidas separadamente
    """

    NOME_BANCO   = "GridSoftware / Roraima"
    CHAVE_SESSAO = "grid_roraima"
    URL_LOGIN    = settings.GRID_URL

    # URL base derivada (para construir URLs internas)
    @property
    def _url_base(self) -> str:
        parsed = urlparse(self.URL_LOGIN)
        return f"{parsed.scheme}://{parsed.netloc}/grid/"

    # ── Seletores — tela de login ─────────────────────────────────────────────
    # Em JSF/PrimeFaces os IDs contêm ':' que em CSS precisam de escape \\:
    SEL_BTN_CONSIGNATARIA = "#j_idt15\\:btnConsignataria"
    SEL_USUARIO           = "#username"
    SEL_SENHA             = "#password"
    SEL_SUBMIT            = "#submit"
    SEL_RECAPTCHA         = ".g-recaptcha"

    # ── Seletores — área logada ───────────────────────────────────────────────
    SEL_AREA_LOGADA = [
        "#j_idt_logout",
        "[id*='sair']",
        "[id*='logout']",
        ".ui-menubar",
        "#formPrincipal",
    ]

    # ── Seletores — consulta de margem ────────────────────────────────────────
    SEL_CAMPO_CPF = [
        "#formConsulta\\:cpf",
        "#formConsulta\\:inputCpf",
        "input[id*='cpf']",
        "input[name*='cpf']",
        "input[placeholder*='CPF']",
    ]
    SEL_BTN_CONSULTAR = [
        "#formConsulta\\:btnConsultar",
        "button:has-text('Consultar')",
        "input[value='Consultar']",
        "a:has-text('Consultar')",
    ]
    SEL_RESULTADO = [
        "#formResultado",
        ".ui-datatable",
        "#tblMargem",
        ".resultado-margem",
        "#panelResultado",
    ]

    # ── Seletores — abas de margem ────────────────────────────────────────────
    SEL_ABA_EMPRESTIMO = [
        "a:has-text('Margem de Empréstimo')",
        "a:has-text('Empréstimo')",
        ".ui-tabview-nav li:first-child a",
        "#tabEmprestimo",
    ]
    SEL_ABA_CARTAO = [
        "a:has-text('Margem de Cartão')",
        "a:has-text('Cartão')",
        ".ui-tabview-nav li:nth-child(2) a",
        "#tabCartao",
    ]
    SEL_VALOR_EMPRESTIMO = [
        "#formResultado\\:margemEmprestimo",
        "#formResultado\\:vlrMargem",
        "td:has-text('Margem Disponível') + td",
        "td:has-text('Margem de Empréstimo') + td",
        ".margem-emprestimo",
    ]
    SEL_VALOR_CARTAO = [
        "#formResultado\\:margemCartao",
        "#formResultado\\:vlrCartao",
        "td:has-text('Margem de Cartão') + td",
        "td:has-text('Cartão de Crédito') + td",
        ".margem-cartao",
    ]

    # ── Verificação de sessão ─────────────────────────────────────────────────

    def _esta_logado(self, page) -> bool:
        """
        Sessão ativa se URL não contém 'login' e algum elemento
        da área logada está presente.
        """
        if "login" in page.url.lower():
            return False
        return self._primeiro_seletor(page, self.SEL_AREA_LOGADA) is not None

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _fazer_login(self, page) -> None:
        """
        Fluxo completo de autenticação no SIGAC-Web:
          seleção de perfil → credenciais → reCAPTCHA → submit
        """
        logger.info("[GridSoftware] Navegando para tela de login.")
        page.goto(self.URL_LOGIN, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.5)

        # ── Passo 1: selecionar perfil Consignatária ──────────────────────────
        self._clicar_btn_consignataria(page)

        # ── Passo 2: preencher credenciais ────────────────────────────────────
        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_EL)

        page.click(self.SEL_USUARIO)
        digitar_lento(page, self.SEL_USUARIO, settings.GRID_LOGIN)
        pausa_humana(0.5, 1.0)

        page.click(self.SEL_SENHA)
        digitar_lento(page, self.SEL_SENHA, settings.GRID_SENHA)
        pausa_humana(0.5, 1.0)

        # ── Passo 3: resolver reCAPTCHA ───────────────────────────────────────
        self._resolver_captcha_se_presente(page)

        # ── Passo 4: submeter formulário ──────────────────────────────────────
        page.click(self.SEL_SUBMIT)
        logger.info("[GridSoftware] Formulário submetido — aguardando redirecionamento.")

        try:
            # Aguarda URL mudar para fora da tela de login
            page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('login')",
                timeout=20_000,
            )
        except Exception:
            # Verifica se foi exibida mensagem de erro
            erro_txt = self._texto_seletor(page, [
                ".ui-messages-error",
                ".ui-message-error-detail",
                "#mensagemErro",
                ".login-error",
                "[class*='erro']",
            ])
            if erro_txt:
                raise RuntimeError(f"Login GridSoftware falhou: {erro_txt}")
            # Espera genérica por networkidle como último recurso
            page.wait_for_load_state("networkidle", timeout=15_000)

        pausa_humana(1.0, 2.0)
        logger.info("[GridSoftware] Login concluído. URL: %s", page.url)

    def _clicar_btn_consignataria(self, page) -> None:
        """
        Clica no botão de seleção de perfil 'Consignatária'.
        Tenta o seletor exato e fallbacks por texto.
        """
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
            logger.info("[GridSoftware] Perfil 'Consignatária' selecionado.")
        else:
            logger.warning(
                "[GridSoftware] Botão 'Consignatária' não encontrado — "
                "continuando sem seleção de perfil."
            )

    def _resolver_captcha_se_presente(self, page) -> None:
        """
        Detecta reCAPTCHA e resolve via 2Captcha se presente.
        Não levanta erro se não houver reCAPTCHA.
        """
        solver = TwoCaptchaSolver()
        sitekey = solver.extrair_sitekey(page)

        if not sitekey:
            logger.info("[GridSoftware] Nenhum reCAPTCHA detectado na página de login.")
            return

        logger.info("[GridSoftware] reCAPTCHA detectado. Resolvendo via 2Captcha...")
        token = solver.resolver(sitekey=sitekey, page_url=page.url)
        solver.injetar_token(page, token)
        pausa_humana(1.0, 2.0)
        logger.info("[GridSoftware] Token reCAPTCHA injetado com sucesso.")

    # ── Navegação para consulta ───────────────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        """
        Navega para a tela de consulta de margem via menu ou URL direta.
        """
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
            logger.info("[GridSoftware] Navegou para consulta via menu.")
            return

        # Fallback para URL direta do SIGAC-Web
        url_consulta = urljoin(self._url_base, "margem/consultaMargem.seam")
        logger.warning(
            "[GridSoftware] Menu não localizado — tentando URL direta: %s", url_consulta
        )
        page.goto(url_consulta, wait_until="networkidle", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

    # ── Extração ──────────────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        """
        Fluxo completo de consulta: navega, insere CPF, lê as duas abas.
        """
        self._navegar_para_consulta(page)

        # ── Campo CPF ─────────────────────────────────────────────────────────
        campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF)
        if not campo_cpf:
            return resultado_erro(
                "Campo CPF não encontrado na tela de consulta.",
                cpf, self.NOME_BANCO,
            )

        digitar_lento(page, campo_cpf, formatar_cpf(cpf))
        pausa_humana(0.5, 1.0)

        # ── Submit ────────────────────────────────────────────────────────────
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
                "não encontrado", "sem margem", "não possui", "nenhum registro",
            ]):
                return resultado_sem_margem(cpf, self.NOME_BANCO)
            return resultado_erro(
                "Resultado não carregou no tempo esperado.", cpf, self.NOME_BANCO
            )

        pausa_humana(0.3, 0.8)

        # ── Dados gerais do servidor ──────────────────────────────────────────
        nome_txt = self._texto_seletor(page, [
            "#formResultado\\:nome",
            "#formResultado\\:nomeServidor",
            "td:has-text('Nome') + td",
            ".nome-servidor",
        ])
        orgao_txt = self._texto_seletor(page, [
            "#formResultado\\:orgao",
            "#formResultado\\:nomeOrgao",
            "td:has-text('Órgão') + td",
            ".orgao-servidor",
        ])

        # ── Leitura das abas de margem ────────────────────────────────────────
        margem_emprestimo = self._ler_aba(
            page,
            seletores_aba=self.SEL_ABA_EMPRESTIMO,
            seletores_valor=self.SEL_VALOR_EMPRESTIMO,
            nome_aba="Margem de Empréstimo",
        )
        margem_cartao = self._ler_aba(
            page,
            seletores_aba=self.SEL_ABA_CARTAO,
            seletores_valor=self.SEL_VALOR_CARTAO,
            nome_aba="Margem de Cartão",
        )

        status = (
            "sucesso"
            if (margem_emprestimo is not None or margem_cartao is not None)
            else "sem_margem"
        )

        logger.info(
            "[GridSoftware] CPF %s | Empréstimo: R$ %s | Cartão: R$ %s | status: %s",
            cpf, margem_emprestimo, margem_cartao, status,
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

    # ── Helper: ler uma aba de margem ─────────────────────────────────────────

    def _ler_aba(
        self,
        page,
        seletores_aba: list[str],
        seletores_valor: list[str],
        nome_aba: str,
    ) -> Optional[float]:
        """
        Clica na aba de margem e extrai o valor numérico.

        Args:
            seletores_aba:   Lista de seletores CSS para localizar a aba.
            seletores_valor: Lista de seletores CSS para o valor monetário.
            nome_aba:        Nome legível para logging.

        Returns:
            Valor float da margem ou None se não encontrado.
        """
        # Clica na aba (se encontrada)
        sel_aba = self._primeiro_seletor(page, seletores_aba)
        if sel_aba:
            try:
                page.click(sel_aba)
                pausa_humana(0.5, 1.0)
                logger.debug("[GridSoftware] Aba '%s' clicada.", nome_aba)
            except Exception as exc:
                logger.warning(
                    "[GridSoftware] Não foi possível clicar na aba '%s': %s",
                    nome_aba, exc,
                )
        else:
            logger.debug("[GridSoftware] Aba '%s' não localizada.", nome_aba)

        # Extrai valor
        texto = self._texto_seletor(page, seletores_valor)
        valor = parse_moeda(texto)

        logger.debug(
            "[GridSoftware] '%s': texto='%s' → valor=%s", nome_aba, texto, valor
        )
        return valor
