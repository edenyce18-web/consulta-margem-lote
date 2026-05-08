"""
scraper/rf1consig_adapter.py
──────────────────────────────
Adaptador para o portal RF1Consig — Consignatária Prefeitura de Boa Vista/RR.

URL padrão: https://boavista.rf1consig.com.br/SGConsignataria/GESTOR/CADPessoaListar.aspx

Login:
  - CPF do usuário (formatado automaticamente)
  - Senha
  - Consignatária (dropdown ASP.NET — auto-selecionada se só houver uma opção,
    ou selecionada pelo valor/texto informado via parâmetro "consignataria=" na URL)
  - CAPTCHA de imagem (resolvido automaticamente via 2Captcha quando configurado,
    ou com fallback de 3 tentativas usando OCR básico de dígitos)

Reutilização de sessão:
  O login é feito uma única vez por lote. Entre CPFs, apenas navega para a
  página de consulta e extrai os dados sem re-autenticar.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

from app.config import settings
from app.scraper.base_adapter import (
    BaseScraperAdapter,
    TIMEOUT_NAV, TIMEOUT_EL, TIMEOUT_CONS,
)
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    formatar_cpf, limpar_cpf, validar_cpf, pausa_humana, digitar_lento,
    parse_moeda, resultado_erro, resultado_sem_margem, resultado_cpf_invalido,
    clicar_seguro, salvar_screenshot,
)
from pathlib import Path

logger = logging.getLogger(__name__)


@AdapterManager.registrar("bv")
class RF1ConsigBoaVistaAdapter(BaseScraperAdapter):
    """
    Adaptador para RF1Consig — Portal Consignatário da Prefeitura de Boa Vista.
    Registrado como chave 'bv'.
    """

    NOME_BANCO   = "RF1Consig / Boa Vista"
    CHAVE_SESSAO = "rf1consig_bv"

    _URL_LOGIN_DEFAULT = (
        "https://boavista.rf1consig.com.br/SGConsignataria/"
        "ConsigAcessoUsuarioLogar.aspx"
    )
    _URL_CONSULTA_DEFAULT = (
        "https://boavista.rf1consig.com.br/SGConsignataria/"
        "GESTOR/CADPessoaListar.aspx"
    )

    # ── Seletores de login (ASP.NET WebForms — IDs renderizados) ─────────────
    # O padrão ASP.NET converte "ctl00$ContentPlaceHolder1$txtCPF"
    # para o ID "ContentPlaceHolder1_txtCPF" no HTML renderizado.

    SEL_CPF    = [
        "#ContentPlaceHolder1_txtCPF",
        "#ctl00_ContentPlaceHolder1_txtCPF",
        "input[id*='txtCPF']",
        "input[id*='txtUsuario']",
    ]
    SEL_SENHA  = [
        "#ContentPlaceHolder1_txtSenha",
        "#ctl00_ContentPlaceHolder1_txtSenha",
        "input[id*='txtSenha'][type='password']",
        "input[type='password']",
    ]
    SEL_CONSIG = [
        "#ContentPlaceHolder1_ddlConsignataria",
        "#ctl00_ContentPlaceHolder1_ddlConsignataria",
        "select[id*='ddlConsignataria']",
        "select[id*='Consignataria']",
    ]
    SEL_CAPTCHA_IMG = [
        "img[src*='Captcha.aspx']",
        "img[src*='captcha']",
        "#ContentPlaceHolder1_imgCaptcha",
        "img[id*='imgCaptcha']",
    ]
    SEL_CAPTCHA_INPUT = [
        "#ContentPlaceHolder1_txtCodSeguranca",
        "#ctl00_ContentPlaceHolder1_txtCodSeguranca",
        "input[id*='txtCodSeguranca']",
        "input[id*='CodSeguranca']",
        "input[id*='Captcha']",
    ]
    SEL_BTN_LOGIN = [
        "#ContentPlaceHolder1_btnEntrar",
        "#ctl00_ContentPlaceHolder1_btnEntrar",
        "input[id*='btnEntrar']",
        "input[type='submit']",
        "a[id*='btnEntrar']",
        "button:has-text('Entrar')",
    ]

    # ── Seletores de área logada ──────────────────────────────────────────────
    SEL_AREA_LOGADA = [
        "a[href*='Sair']", "a[href*='Logout']", "a[href*='sair']",
        "a:has-text('Sair')", "a:has-text('Logout')", "a:has-text('Encerrar')",
        "[id*='lnkSair']", "[id*='btnSair']", "[id*='lnkLogout']",
        ".menu-topo", "#divMenu", "#menuPrincipal",
    ]
    SEL_ERRO_LOGIN = [
        ".MensagemErro", "#ContentPlaceHolder1_lblMensagem",
        "[id*='lblMensagem']", "[id*='lblErro']",
        ".alert-danger", "[class*='erro']",
        "span:has-text('inválid')", "span:has-text('incorret')",
        "span:has-text('bloqueado')",
    ]

    # ── Seletores de consulta de CPF ──────────────────────────────────────────
    SEL_MENU_CONSULTA = [
        "a:has-text('Consulta de Margem')",
        "a:has-text('Consultar Margem')",
        "a:has-text('Margem Consignável')",
        "a:has-text('Consulta Margem')",
        "a[href*='ConsultaMargem']",
        "a[href*='ConsultarMargem']",
        "a[href*='Margem']",
        "a:has-text('Consulta')",
    ]
    SEL_CAMPO_CPF_CONSULTA = [
        "#ContentPlaceHolder1_txtCPF",
        "#ContentPlaceHolder1_txtCpfServidor",
        "#ContentPlaceHolder1_txtPesquisa",
        "#ContentPlaceHolder1_txtPesquisaCPF",
        "input[id*='txtCPF']",
        "input[id*='txtCpf']",
        "input[id*='CPF']",
        "input[id*='Cpf']",
        "input[placeholder*='CPF']",
        "input[placeholder*='cpf']",
    ]
    SEL_CAMPO_MATRICULA_CONSULTA = [
        "#ContentPlaceHolder1_txtMatricula",
        "#ContentPlaceHolder1_txtMatriculaServidor",
        "#ContentPlaceHolder1_txtPesquisaMatricula",
        "input[id*='txtMatricula']",
        "input[id*='Matricula']",
        "input[id*='Matrícula']",
        "input[placeholder*='Matrícula']",
        "input[placeholder*='Matricula']",
        "input[placeholder*='matrícula']",
        "input[placeholder*='matricula']",
    ]
    SEL_CAMPO_BUSCA_GERAL = [
        "#ContentPlaceHolder1_txtPesquisa",
        "#ContentPlaceHolder1_txtFiltro",
        "input[id*='txtPesquisa']",
        "input[id*='txtFiltro']",
        "input[id*='txtBusca']",
        "input[placeholder*='Pesquisa']",
        "input[placeholder*='Busca']",
    ]
    SEL_BTN_CONSULTAR = [
        "#ContentPlaceHolder1_btnConsultar",
        "#ContentPlaceHolder1_btnPesquisar",
        "input[id*='btnConsultar']",
        "input[id*='btnPesquisar']",
        "button:has-text('Consultar')",
        "button:has-text('Pesquisar')",
        "a:has-text('Consultar')",
    ]
    SEL_RESULTADO = [
        "#ContentPlaceHolder1_gridResultado",
        "#ContentPlaceHolder1_tblMargem",
        "#ContentPlaceHolder1_panelResultado",
        "[id*='gridResultado']",
        "[id*='tblMargem']",
        "[id*='panelResultado']",
        "table:has(td)",
    ]

    def __init__(
        self,
        credencial: Optional[dict] = None,
        usuario_id: Optional[str] = None,
    ):
        super().__init__(credencial, usuario_id=usuario_id)
        raw_url = (credencial or {}).get("url") or settings.RF1BV_URL or self._URL_CONSULTA_DEFAULT
        # Extrai parâmetro "consignataria=" da URL (se informado pelo usuário)
        self._consignataria_hint = self._extrair_param_consignataria(raw_url)
        # URL limpa (sem parâmetros customizados)
        self.URL_LOGIN = raw_url.split("?")[0] if "consignataria=" in raw_url else raw_url

    @staticmethod
    def _extrair_param_consignataria(url: str) -> Optional[str]:
        """Extrai o valor de consignataria= da querystring da URL."""
        qs = parse_qs(urlparse(url).query)
        return (qs.get("consignataria") or [None])[0]

    @property
    def _login(self) -> str:
        return self._credencial.get("login") or ""

    @property
    def _senha(self) -> str:
        return self._credencial.get("senha") or ""

    @property
    def _base_url(self) -> str:
        p = urlparse(self.URL_LOGIN)
        path_parts = p.path.rsplit("/", 1)
        base_path = path_parts[0] + "/" if len(path_parts) > 1 else "/"
        return f"{p.scheme}://{p.netloc}{base_path}"

    # ── Verificação de sessão ─────────────────────────────────────────────────

    def _esta_logado(self, page) -> bool:
        url = page.url.lower()
        if "logar" in url or "login" in url:
            return False
        return self._primeiro_seletor(page, self.SEL_AREA_LOGADA) is not None

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _fazer_login(self, page) -> None:
        logger.info("[RF1BV] Acessando tela de login: %s", self.URL_LOGIN)
        page.goto(self.URL_LOGIN, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

        # ── CPF ───────────────────────────────────────────────────────────────
        sel_cpf = self._primeiro_seletor(page, self.SEL_CPF)
        if not sel_cpf:
            raise RuntimeError("[RF1BV] Campo CPF não encontrado na tela de login.")
        page.fill(sel_cpf, "")
        digitar_lento(page, sel_cpf, formatar_cpf(self._login))
        pausa_humana(0.3, 0.7)

        # ── Senha ─────────────────────────────────────────────────────────────
        sel_senha = self._primeiro_seletor(page, self.SEL_SENHA)
        if not sel_senha:
            raise RuntimeError("[RF1BV] Campo senha não encontrado na tela de login.")
        page.fill(sel_senha, "")
        digitar_lento(page, sel_senha, self._senha)
        pausa_humana(0.3, 0.7)

        # ── Consignatária ─────────────────────────────────────────────────────
        sel_consig = self._primeiro_seletor(page, self.SEL_CONSIG, exigir_visivel=False)
        if sel_consig:
            self._selecionar_consignataria(page, sel_consig)
            pausa_humana(0.3, 0.7)

        # ── CAPTCHA ───────────────────────────────────────────────────────────
        self._resolver_captcha(page)
        pausa_humana(0.5, 1.0)

        # ── Clica em Entrar ───────────────────────────────────────────────────
        sel_btn = self._primeiro_seletor(page, self.SEL_BTN_LOGIN, exigir_visivel=False)
        if sel_btn:
            self._clicar_com_fallback(page, sel_btn, timeout=8_000)
        else:
            page.keyboard.press("Enter")

        logger.info("[RF1BV] Aguardando redirecionamento pós-login...")
        try:
            page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('logar')",
                timeout=30_000,
            )
        except Exception:
            # Verifica se apareceu mensagem de erro de login
            erro_txt = self._texto_seletor(page, self.SEL_ERRO_LOGIN)
            if erro_txt:
                raise RuntimeError(
                    f"[RF1BV] Login falhou. Mensagem do portal: {erro_txt}"
                )
            # Verifica se área logada apareceu mesmo assim
            if not self._esta_logado(page):
                salvar_screenshot(page, "rf1bv_login_falhou", Path("/tmp/pw_sessions"))
                raise RuntimeError(
                    f"[RF1BV] Login não concluído. URL atual: {page.url}. "
                    "Verifique CPF, senha e consignatária nas credenciais."
                )

        pausa_humana(1.0, 2.0)
        logger.info("[RF1BV] Login concluído. URL: %s", page.url)

    def _selecionar_consignataria(self, page, sel_consig: str) -> None:
        """Seleciona a consignatária correta no dropdown."""
        try:
            # Lista todas as opções disponíveis
            opcoes = page.locator(f"{sel_consig} option").all()
            if not opcoes:
                logger.warning("[RF1BV] Dropdown de consignatária está vazio.")
                return

            # Filtra opções válidas (ignora opção vazia/placeholder)
            opcoes_validas = []
            for op in opcoes:
                val = op.get_attribute("value") or ""
                txt = (op.text_content() or "").strip()
                if val and val not in ("0", "", "-1"):
                    opcoes_validas.append((val, txt))

            if not opcoes_validas:
                logger.warning("[RF1BV] Nenhuma consignatária válida no dropdown.")
                return

            logger.info("[RF1BV] Consignatárias disponíveis: %s", opcoes_validas)

            # Se o usuário especificou uma consignatária na URL, tenta corresponder
            if self._consignataria_hint:
                hint = self._consignataria_hint.lower()
                match = next(
                    ((v, t) for v, t in opcoes_validas
                     if hint in t.lower() or hint == v.lower()),
                    None,
                )
                if match:
                    page.select_option(sel_consig, value=match[0])
                    logger.info("[RF1BV] Consignatária selecionada por hint: %s", match[1])
                    return

            # Sem hint: seleciona a primeira opção válida
            page.select_option(sel_consig, value=opcoes_validas[0][0])
            logger.info("[RF1BV] Consignatária selecionada (1ª opção): %s", opcoes_validas[0][1])

        except Exception as exc:
            logger.warning("[RF1BV] Erro ao selecionar consignatária: %s", exc)

    def _resolver_captcha(self, page) -> None:
        """
        Tenta resolver o CAPTCHA de imagem.
        - Com TWOCAPTCHA_API_KEY configurada: usa 2Captcha (automático).
        - Sem chave: lança RuntimeError orientando o usuário a configurar.
        """
        sel_img = self._primeiro_seletor(page, self.SEL_CAPTCHA_IMG, exigir_visivel=False)
        sel_input = self._primeiro_seletor(page, self.SEL_CAPTCHA_INPUT)

        if not sel_img or not sel_input:
            logger.info("[RF1BV] CAPTCHA não detectado na página — prosseguindo sem.")
            return

        logger.info("[RF1BV] CAPTCHA detectado. Iniciando resolução automática...")

        if not settings.TWOCAPTCHA_API_KEY:
            raise RuntimeError(
                "[RF1BV] Este portal requer CAPTCHA. "
                "Configure TWOCAPTCHA_API_KEY no arquivo .env da VPS para resolver automaticamente."
            )

        from app.scraper.captcha import ImageCaptchaSolver, CaptchaUnsolvableError

        solver = ImageCaptchaSolver()
        # Tenta até 3 vezes (CAPTCHA pode ser ilegível na 1ª tentativa)
        for tentativa in range(1, 4):
            try:
                texto = solver.resolver_elemento(page, sel_img)
                logger.info("[RF1BV] CAPTCHA resolvido na tentativa %d: '%s'", tentativa, texto)
                page.fill(sel_input, "")
                page.fill(sel_input, texto.strip())
                return
            except CaptchaUnsolvableError:
                logger.warning("[RF1BV] CAPTCHA ilegível (tentativa %d) — recarregando...", tentativa)
                # Clica na imagem para gerar novo CAPTCHA
                try:
                    page.locator(sel_img).first.click()
                    pausa_humana(1.0, 2.0)
                except Exception:
                    pass
            except Exception as exc:
                logger.error("[RF1BV] Erro ao resolver CAPTCHA (tentativa %d): %s", tentativa, exc)
                if tentativa == 3:
                    raise

        raise RuntimeError("[RF1BV] Falha ao resolver CAPTCHA após 3 tentativas.")

    # ── Navegação para consulta ───────────────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        """Navega até a página de consulta de margem."""
        # Tenta clicar no menu "Consulta de Margem"
        sel_menu = self._primeiro_seletor(page, self.SEL_MENU_CONSULTA, exigir_visivel=False)
        if sel_menu:
            clicou = self._clicar_com_fallback(page, sel_menu, timeout=8_000)
            if clicou:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                pausa_humana(0.5, 1.0)
                logger.info("[RF1BV] Navegou para consulta via menu. URL: %s", page.url)
                return

        # Fallback: URL direta com padrões comuns do RF1Consig
        for path in [
            "GESTOR/CADPessoaListar.aspx",
            "CADPessoaListar.aspx",
            "ConsigConsultaMargem.aspx",
            "ConsigConsultarMargemServidor.aspx",
            "ConsigConsultaMargemServidor.aspx",
            "ConsigMargem.aspx",
        ]:
            url_tentativa = urljoin(self._base_url, path)
            try:
                page.goto(url_tentativa, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
                pausa_humana(0.5, 1.0)
                if "logar" not in page.url.lower() and "login" not in page.url.lower():
                    logger.info("[RF1BV] Página de consulta acessada via URL direta: %s", url_tentativa)
                    return
            except Exception:
                continue

        logger.error("[RF1BV] Não foi possível alcançar a página de consulta. URL: %s", page.url)

    # ── Identificador CPF/matrícula ───────────────────────────────────────────

    def _normalizar_identificador(self, valor: str) -> tuple[str, str, Optional[dict]]:
        """Retorna (tipo, identificador, erro) para CPF ou matrícula."""
        bruto = str(valor or "").strip()
        if bruto.lower().startswith(("matricula:", "matrícula:")):
            matricula_forcada = bruto.split(":", 1)[1].strip()
            if matricula_forcada:
                return "matricula", re.sub(r"\s+", "", matricula_forcada), None

        somente_digitos = limpar_cpf(bruto)

        if len(somente_digitos) == 11:
            if not validar_cpf(somente_digitos):
                return "cpf", somente_digitos, resultado_cpf_invalido(
                    somente_digitos, self.NOME_BANCO
                )
            return "cpf", somente_digitos, None

        # Matrículas costumam ser numéricas, mas mantemos letras se o portal usar
        # prefixos/sufixos. O preenchimento usa o valor original sem espaços.
        matricula = re.sub(r"\s+", "", bruto)
        if matricula:
            return "matricula", matricula, None

        return "matricula", bruto, resultado_erro(
            "Informe CPF válido ou matrícula.", bruto, self.NOME_BANCO
        )

    def consultar_com_page(self, page, cpf: str, context=None) -> dict:
        """Consulta CPF ou matrícula usando uma página autenticada reutilizável."""
        tipo, identificador, erro = self._normalizar_identificador(cpf)
        if erro:
            return erro

        if not self._esta_logado(page):
            logger.info(
                "[RF1BV] Sessão expirada — re-autenticando para %s %s",
                tipo, identificador,
            )
            self._invalidar_sessao()
            self._fazer_login(page)
            if context:
                self._salvar_sessao(context)

        try:
            resultado = self._extrair_margem(page, identificador)
            if "login" in page.url.lower() or "logar" in page.url.lower():
                self._invalidar_sessao()
                self._fazer_login(page)
                if context:
                    self._salvar_sessao(context)
                resultado = self._extrair_margem(page, identificador)
            return resultado
        except Exception as exc:
            logger.error("[RF1BV] Erro ao consultar %s %s: %s", tipo, identificador, exc)
            return resultado_erro(str(exc), identificador, self.NOME_BANCO)

    # ── Extração de margem ────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        """
        Consulta CPF ou matrícula e extrai os dados de margem consignável.
        Reutiliza a página de consulta se o campo de busca já estiver visível.
        """
        tipo, identificador, erro = self._normalizar_identificador(cpf)
        if erro:
            return erro

        seletores_preferidos = (
            self.SEL_CAMPO_CPF_CONSULTA if tipo == "cpf"
            else self.SEL_CAMPO_MATRICULA_CONSULTA
        )
        sel_busca = self._primeiro_seletor(
            page, [*seletores_preferidos, *self.SEL_CAMPO_BUSCA_GERAL],
            exigir_visivel=False,
        )

        if not sel_busca:
            self._navegar_para_consulta(page)
            sel_busca = self._primeiro_seletor(
                page, [*seletores_preferidos, *self.SEL_CAMPO_BUSCA_GERAL],
                exigir_visivel=False,
            )

        if not sel_busca:
            salvar_screenshot(page, "rf1bv_sem_campo_busca", Path("/tmp/pw_sessions"))
            return resultado_erro(
                f"[RF1BV] Campo de CPF/matrícula não encontrado na página de consulta (URL: {page.url}).",
                identificador, self.NOME_BANCO,
            )

        valor_busca = formatar_cpf(identificador) if tipo == "cpf" else identificador
        try:
            loc = page.locator(sel_busca).first
            loc.triple_click(timeout=3_000)
            loc.fill(valor_busca)
        except Exception:
            page.fill(sel_busca, valor_busca)

        pausa_humana(0.2, 0.5)

        # Clica em Consultar
        sel_btn = self._primeiro_seletor(page, self.SEL_BTN_CONSULTAR, exigir_visivel=False)
        clicou = False
        if sel_btn:
            clicou = self._clicar_com_fallback(page, sel_btn, timeout=8_000)
        if not clicou:
            page.locator(sel_busca).first.press("Enter")

        # Aguarda resultado
        try:
            page.wait_for_selector(
                ", ".join(self.SEL_RESULTADO),
                timeout=TIMEOUT_CONS,
            )
        except Exception:
            html = page.content().lower()
            if any(x in html for x in [
                "não encontrado", "sem margem", "nenhum registro",
                "não possui", "cpf não",
            ]):
                return resultado_sem_margem(identificador, self.NOME_BANCO)
            # Pode ter redirecionado para login (sessão expirou)
            if "logar" in page.url.lower():
                raise RuntimeError("Sessão expirada durante consulta — será re-autenticado.")
            return resultado_erro(
                "Timeout aguardando resultado de consulta.", identificador, self.NOME_BANCO,
            )

        pausa_humana(0.3, 0.8)
        self._abrir_detalhe_se_necessario(page)
        return self._extrair_dados(page, identificador)

    def _abrir_detalhe_se_necessario(self, page) -> None:
        """Abre a ficha do servidor quando a busca cai na lista CADPessoaListar."""
        links_detalhe = [
            "a:has-text('Consultar')",
            "a:has-text('Selecionar')",
            "a:has-text('Detalhar')",
            "a:has-text('Visualizar')",
            "input[value*='Consultar']",
            "input[value*='Selecionar']",
            "a[href*='CADPessoa']",
            "a[href*='Margem']",
        ]
        for seletor in links_detalhe:
            try:
                loc = page.locator(seletor)
                if loc.count() == 0 or not loc.first.is_visible():
                    continue
                loc.first.click(timeout=5_000)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                pausa_humana(0.3, 0.8)
                logger.info("[RF1BV] Detalhe do servidor aberto via seletor: %s", seletor)
                return
            except Exception:
                continue

    def _extrair_dados(self, page, cpf: str) -> dict:
        """Extrai os campos de margem da página de resultado."""
        nome     = self._buscar_campo(page, ["Nome", "Servidor", "Nome do Servidor"])
        orgao    = self._buscar_campo(page, ["Órgão", "Orgao", "Secretaria", "Lotação"])
        matricula = self._buscar_campo(page, ["Matrícula", "Matricula"])
        vinculo  = self._buscar_campo(page, ["Vínculo", "Vinculo", "Tipo de Vínculo"])

        margem_emp  = self._buscar_valor_moeda(page, [
            "Margem de Empréstimo", "Margem Empréstimo",
            "Margem Disponível Empréstimo", "Empréstimo",
        ])
        margem_cart = self._buscar_valor_moeda(page, [
            "Margem de Cartão", "Margem Cartão",
            "Margem Disponível Cartão", "Cartão de Crédito",
        ])
        margem_ben  = self._buscar_valor_moeda(page, [
            "Margem de Cartão Benefício", "Margem Cartão Benefício",
            "Cartão Benefício", "Cartao Beneficio",
            "Margem de Benefício", "Margem Benefício",
        ])

        # Fallback: varre todas as células procurando valores R$
        if margem_emp is None and margem_cart is None and margem_ben is None:
            margem_ben = self._extrair_primeiro_valor_moeda(page)

        tem_margem = any(v is not None and v > 0
                         for v in [margem_emp, margem_cart, margem_ben])
        status = "sucesso" if tem_margem else "sem_margem"

        return {
            "cpf":              cpf,
            "status_consulta":  status,
            "mensagem_erro":    None,
            "nome_titular":     nome,
            "orgao":            orgao,
            "matricula":        matricula,
            "tipo_vinculo":     vinculo,
            "margem_disponivel": margem_emp,
            "margem_cartao":    margem_cart,
            "margem_beneficio": margem_ben,
            "emprestimo_situacao":       "Disponível" if margem_emp and margem_emp > 0 else None,
            "cartao_credito_situacao":   "Disponível" if margem_cart and margem_cart > 0 else None,
            "cartao_beneficio_situacao": "Disponível" if margem_ben and margem_ben > 0 else None,
            "banco": self.NOME_BANCO,
            "dados_brutos": json.dumps({
                "margem_emprestimo": str(margem_emp),
                "margem_cartao":     str(margem_cart),
                "margem_beneficio":  str(margem_ben),
                "url":               page.url,
            }, ensure_ascii=False),
        }

    # ── Helpers de extração ───────────────────────────────────────────────────

    def _buscar_campo(self, page, rotulos: list[str]) -> Optional[str]:
        """
        Procura o valor de um campo em tabelas HTML.
        Estratégias:
          1. td com o rótulo → td seguinte (padrão tabela label/valor)
          2. th com o rótulo → td na mesma linha
        """
        for rotulo in rotulos:
            # Estratégia 1: td:has-text + sibling td
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

            # Estratégia 2: th:has-text
            try:
                loc = page.locator(f"th:has-text('{rotulo}')")
                if loc.count() > 0:
                    row = loc.first.locator("xpath=..").locator("td").first
                    valor = (row.text_content() or "").strip()
                    if valor:
                        return valor
            except Exception:
                pass

        return None

    def _buscar_valor_moeda(self, page, rotulos: list[str]) -> Optional[float]:
        """Busca valor monetário (R$) associado a um rótulo."""
        for rotulo in rotulos:
            try:
                cells = page.locator("td").all()
                for i, cell in enumerate(cells):
                    txt = (cell.text_content() or "").strip().rstrip(":")
                    if rotulo.lower() in txt.lower() and i + 1 < len(cells):
                        proximo = (cells[i + 1].text_content() or "").strip()
                        valor = parse_moeda(proximo)
                        if valor is not None:
                            return valor
                        # Pode estar na mesma célula após "R$"
                        match = re.search(r"R\$\s*([\d.,]+)", txt)
                        if match:
                            return parse_moeda(match.group(1))
            except Exception:
                pass
        return None

    def _extrair_primeiro_valor_moeda(self, page) -> Optional[float]:
        """Extrai o primeiro valor R$ encontrado na página como fallback."""
        try:
            html = page.content()
            matches = re.findall(r"R\$\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))", html)
            for m in matches:
                val = parse_moeda(m)
                if val and val > 0:
                    return val
        except Exception:
            pass
        return None
