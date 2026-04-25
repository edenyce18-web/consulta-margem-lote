"""
scraper.py — Motor de consulta de margem consignada via Playwright.

Adaptadores disponíveis:
  - PortalExemploAdapter   : portal fictício para testes sem credenciais reais
  - AkiCapitalAdapter      : portal AkiCapital (login próprio, sem CAPTCHA)
  - GridSoftwareAdapter    : portal GridSoftware/Roraima (reCAPTCHA via 2Captcha)
  - BancoBrasilAdapter     : esqueleto para integração BB (customizar seletores)
  - CEFAdapter             : esqueleto para integração CEF (customizar seletores)

Estratégia de sessão:
  Cada adaptador mantém o estado de sessão em disco (SESSION_DIR) para
  reutilizar o login entre CPFs do mesmo lote, evitando overhead de
  autenticação repetida e reduzindo risco de bloqueio.
"""

import os
import re
import json
import time
import logging
import random
import httpx
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

AKICAPITAL_URL_LOGIN = settings.AKICAPITAL_URL
GRID_URL_LOGIN       = settings.GRID_URL

# Timeouts (ms)
TIMEOUT_NAVEGACAO  = 30_000
TIMEOUT_ELEMENTO   = 20_000
TIMEOUT_CONSULTA   = 40_000

# Diretório para salvar estados de sessão Playwright
SESSION_DIR = Path(settings.SESSION_DIR)
SESSION_DIR.mkdir(parents=True, exist_ok=True)


# ── Utilidades gerais ─────────────────────────────────────────────────────────

def limpar_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def formatar_cpf(cpf: str) -> str:
    """Retorna CPF no formato 000.000.000-00."""
    c = limpar_cpf(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}" if len(c) == 11 else cpf


def validar_cpf(cpf: str) -> bool:
    cpf = limpar_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        soma = sum(int(cpf[j]) * (i + 1 - j) for j in range(i))
        digito = (soma * 10 % 11) % 10
        if digito != int(cpf[i]):
            return False
    return True


def resultado_erro(mensagem: str, cpf: str, banco: str = "") -> dict:
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


def _parse_moeda(texto: Optional[str]) -> Optional[float]:
    """Converte 'R$ 1.234,56' → 1234.56."""
    if not texto:
        return None
    try:
        limpo = re.sub(r"[R$\s\xa0]", "", texto).replace(".", "").replace(",", ".")
        return float(limpo)
    except (ValueError, AttributeError):
        return None


def _pausa_humana(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _salvar_screenshot_erro(page, nome: str) -> None:
    """Salva screenshot para debug quando ocorre um erro."""
    try:
        caminho = SESSION_DIR / f"erro_{nome}_{int(time.time())}.png"
        page.screenshot(path=str(caminho), full_page=True)
        logger.warning("Screenshot de erro salvo em: %s", caminho)
    except Exception:
        pass


# ── Solver 2Captcha ───────────────────────────────────────────────────────────

class TwoCaptchaSolver:
    """
    Integração com a API do 2Captcha para resolução de reCAPTCHA v2.

    Configuração:
        TWOCAPTCHA_API_KEY  → chave obtida em 2captcha.com
        TWOCAPTCHA_TIMEOUT_S → máximo de segundos aguardando solução (padrão: 120)

    Uso:
        solver = TwoCaptchaSolver()
        token = solver.resolver(sitekey="...", page_url="https://...")
        # injeta token e submete o formulário
    """

    API_SUBMIT = "https://2captcha.com/in.php"
    API_RESULT = "https://2captcha.com/res.php"

    def __init__(self):
        self.api_key = settings.TWOCAPTCHA_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "TWOCAPTCHA_API_KEY não configurada. "
                "Defina no .env para usar portais com reCAPTCHA."
            )

    def resolver(self, sitekey: str, page_url: str) -> str:
        """
        Envia o desafio ao 2Captcha e aguarda a solução.

        Returns:
            Token g-recaptcha-response pronto para injeção.

        Raises:
            RuntimeError: se timeout ou erro na API.
        """
        logger.info("Submetendo reCAPTCHA ao 2Captcha. Sitekey: %s", sitekey)

        # 1. Enviar tarefa
        with httpx.Client(timeout=30) as client:
            resp = client.post(self.API_SUBMIT, data={
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": sitekey,
                "pageurl": page_url,
                "json": 1,
            })
            resp.raise_for_status()
            dados = resp.json()

        if dados.get("status") != 1:
            raise RuntimeError(f"2Captcha rejeitou a tarefa: {dados}")

        captcha_id = dados["request"]
        logger.info("Tarefa 2Captcha #%s aceita. Aguardando solução...", captcha_id)

        # 2. Aguardar solução com polling
        deadline = time.time() + settings.TWOCAPTCHA_TIMEOUT_S
        time.sleep(15)  # aguarda processamento inicial

        while time.time() < deadline:
            with httpx.Client(timeout=30) as client:
                resp = client.get(self.API_RESULT, params={
                    "key": self.api_key,
                    "action": "get",
                    "id": captcha_id,
                    "json": 1,
                })
                resp.raise_for_status()
                dados = resp.json()

            if dados.get("status") == 1:
                token = dados["request"]
                logger.info("reCAPTCHA resolvido pelo 2Captcha.")
                return token

            if dados.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                raise RuntimeError("2Captcha não conseguiu resolver o reCAPTCHA.")

            logger.debug("2Captcha ainda processando... aguardando %ds", settings.TWOCAPTCHA_POLL_INTERVAL_S)
            time.sleep(settings.TWOCAPTCHA_POLL_INTERVAL_S)

        raise RuntimeError(f"Timeout: 2Captcha não resolveu em {settings.TWOCAPTCHA_TIMEOUT_S}s.")

    @staticmethod
    def injetar_token(page, token: str) -> None:
        """
        Injeta o token resolvido nos campos ocultos do reCAPTCHA e
        dispara o callback do Google para habilitar o submit.
        """
        page.evaluate(f"""
            document.getElementById('g-recaptcha-response').innerHTML = '{token}';
            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                const callbacks = Object.values(___grecaptcha_cfg.clients || {{}})
                    .flatMap(c => Object.values(c))
                    .filter(v => v && typeof v.callback === 'function');
                callbacks.forEach(c => c.callback('{token}'));
            }}
        """)
        logger.info("Token reCAPTCHA injetado na página.")


# ── Classe base ───────────────────────────────────────────────────────────────

class BaseAdapter(ABC):
    """Interface comum para todos os adaptadores de portal."""

    nome_banco: str = "Banco Genérico"

    @abstractmethod
    def consultar(self, cpf: str) -> dict:
        ...


# ── Adaptador base Playwright com suporte a sessão persistente ────────────────

class PlaywrightAdapter(BaseAdapter):
    """
    Base para adaptadores que usam Playwright.

    Sessão persistente:
        O estado de autenticação (cookies + localStorage) é salvo em disco
        em SESSION_DIR/<chave_sessao>.json e reutilizado entre chamadas.
        Se a sessão expirar (detectado por _esta_logado), faz novo login
        automaticamente.

    Subclasses devem implementar:
        - CHAVE_SESSAO: str       → nome do arquivo de estado
        - URL_LOGIN: str          → URL da página de login
        - _fazer_login(page)      → preencher formulário e confirmar login
        - _esta_logado(page)      → bool indicando sessão ativa
        - _extrair_margem(page, cpf) → dict com resultado
    """

    nome_banco: str = "Portal Real"
    URL_LOGIN: str = ""
    CHAVE_SESSAO: str = "sessao_generica"

    # Subclasses podem sobrescrever para customizar o lançamento do browser
    ARGS_BROWSER: list = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
    ]

    def _caminho_sessao(self) -> Path:
        return SESSION_DIR / f"{self.CHAVE_SESSAO}.json"

    def _criar_contexto(self, playwright):
        """Cria browser context reutilizando sessão salva se existir."""
        browser = playwright.chromium.launch(
            headless=True,
            args=self.ARGS_BROWSER,
        )
        caminho = self._caminho_sessao()
        kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="pt-BR",
        )
        if caminho.exists():
            kwargs["storage_state"] = str(caminho)
            logger.debug("Sessão '%s' carregada do disco.", self.CHAVE_SESSAO)
        return browser, browser.new_context(**kwargs)

    def _salvar_sessao(self, context) -> None:
        try:
            context.storage_state(path=str(self._caminho_sessao()))
            logger.debug("Sessão '%s' salva em disco.", self.CHAVE_SESSAO)
        except Exception as e:
            logger.warning("Não foi possível salvar sessão: %s", e)

    def _invalidar_sessao(self) -> None:
        caminho = self._caminho_sessao()
        if caminho.exists():
            caminho.unlink()
            logger.info("Sessão '%s' removida (login necessário).", self.CHAVE_SESSAO)

    def _esta_logado(self, page) -> bool:
        """Subclasses devem implementar: retorna True se há sessão ativa."""
        return False

    def _fazer_login(self, page) -> None:
        raise NotImplementedError

    def _extrair_margem(self, page, cpf: str) -> dict:
        raise NotImplementedError

    def consultar(self, cpf: str) -> dict:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        cpf_limpo = limpar_cpf(cpf)
        if not validar_cpf(cpf_limpo):
            return {**resultado_erro("CPF inválido", cpf_limpo, self.nome_banco), "status_consulta": "cpf_invalido"}

        try:
            with sync_playwright() as p:
                browser, context = self._criar_contexto(p)
                page = context.new_page()

                try:
                    # Verifica se sessão ainda é válida
                    page.goto(self.URL_LOGIN, wait_until="domcontentloaded", timeout=TIMEOUT_NAVEGACAO)
                    _pausa_humana(0.5, 1.5)

                    if not self._esta_logado(page):
                        logger.info("[%s] Sessão inativa — realizando login.", self.nome_banco)
                        self._invalidar_sessao()
                        self._fazer_login(page)
                        self._salvar_sessao(context)

                    resultado = self._extrair_margem(page, cpf_limpo)
                    return resultado

                except PWTimeout as e:
                    _salvar_screenshot_erro(page, self.CHAVE_SESSAO)
                    self._invalidar_sessao()
                    return resultado_erro(f"Timeout: {e}", cpf_limpo, self.nome_banco)
                except Exception as e:
                    _salvar_screenshot_erro(page, self.CHAVE_SESSAO)
                    self._invalidar_sessao()
                    raise
                finally:
                    browser.close()

        except Exception as e:
            logger.exception("[%s] Erro ao consultar CPF %s: %s", self.nome_banco, cpf_limpo, e)
            return resultado_erro(str(e), cpf_limpo, self.nome_banco)


# ── Adaptador: AkiCapital ─────────────────────────────────────────────────────

class AkiCapitalAdapter(PlaywrightAdapter):
    """
    Adaptador para o portal AkiCapital.

    Fluxo:
      1. GET  → AKICAPITAL_URL (página de login ASP.NET WebForms)
      2. Preenche #EUsuario_CAMPO e #ESenha_CAMPO
      3. Clica #lnkEntrar (LinkButton → postback)
      4. Aguarda redirecionamento para área restrita
      5. Navega para consulta de margem
      6. Insere CPF → captura status de autorização e valor da margem

    Configuração (.env):
      AKICAPITAL_URL    → URL da página de login
      AKICAPITAL_LOGIN  → Usuário (ex: 02622395230_901902)
      AKICAPITAL_SENHA  → Senha
    """

    nome_banco = "AkiCapital"
    CHAVE_SESSAO = "akicapital"
    URL_LOGIN = settings.AKICAPITAL_URL

    # Seletores da página de login
    SEL_USUARIO  = "#EUsuario_CAMPO"
    SEL_SENHA    = "#ESenha_CAMPO"
    SEL_ENTRAR   = "#lnkEntrar"

    def _esta_logado(self, page) -> bool:
        """
        Verifica se já está na área logada checando URL e/ou elementos
        que só existem pós-login.
        """
        url_atual = page.url.lower()
        return "login" not in url_atual and "default" not in url_atual

    def _fazer_login(self, page) -> None:
        logger.info("[AkiCapital] Iniciando login.")

        page.goto(self.URL_LOGIN, wait_until="networkidle", timeout=TIMEOUT_NAVEGACAO)
        _pausa_humana(1, 2)

        # Aguarda campo de usuário estar visível
        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_ELEMENTO)

        # Preenche credenciais com digitação humana (evita detecção por bots)
        page.click(self.SEL_USUARIO)
        page.fill(self.SEL_USUARIO, "")
        page.type(self.SEL_USUARIO, settings.AKICAPITAL_LOGIN, delay=random.randint(50, 120))

        _pausa_humana(0.5, 1.0)

        page.click(self.SEL_SENHA)
        page.fill(self.SEL_SENHA, "")
        page.type(self.SEL_SENHA, settings.AKICAPITAL_SENHA, delay=random.randint(50, 120))

        _pausa_humana(0.5, 1.2)

        # Clica no botão de login (LinkButton ASP.NET → dispara postback)
        page.click(self.SEL_ENTRAR)

        # Aguarda navegação pós-login (ASP.NET pode usar postback + redirect)
        try:
            page.wait_for_url("**/AreaRestrita/**", timeout=15_000)
        except Exception:
            # Alguns portais redirecionam para URL diferente; tenta aguardar
            # pelo desaparecimento do campo de senha (indica troca de página)
            page.wait_for_selector(self.SEL_SENHA, state="hidden", timeout=15_000)

        _pausa_humana(1, 2)
        logger.info("[AkiCapital] Login concluído. URL: %s", page.url)

    def _navegar_consulta_margem(self, page) -> None:
        """
        Navega até a tela de consulta de margem após o login.
        Adaptar seletores/URL conforme layout real do portal.
        """
        # Tenta localizar link/menu de consulta por texto
        seletores_menu = [
            "a:has-text('Consulta de Margem')",
            "a:has-text('Margem')",
            "a:has-text('Consultar')",
            "#mnuConsultaMargem",
            ".menu-margem a",
        ]
        for sel in seletores_menu:
            if page.locator(sel).count() > 0:
                page.click(sel)
                page.wait_for_load_state("networkidle", timeout=TIMEOUT_NAVEGACAO)
                _pausa_humana(1, 2)
                return

        # Fallback: tenta URL direta conhecida do portal
        page.goto(self.URL_LOGIN.replace("Login.aspx", "ConsultaMargem.aspx"),
                  wait_until="networkidle", timeout=TIMEOUT_NAVEGACAO)
        _pausa_humana(1, 2)

    def _extrair_margem(self, page, cpf: str) -> dict:
        """Navega à consulta de margem, insere CPF e extrai resultado."""
        self._navegar_consulta_margem(page)

        # ── Inserção do CPF ───────────────────────────────────────────────
        # Mapeamento de seletores possíveis para o campo CPF
        seletores_cpf = ["#ECPF_CAMPO", "#cpf", "input[name*='CPF']", "input[name*='cpf']"]
        campo_cpf = None
        for sel in seletores_cpf:
            if page.locator(sel).count() > 0:
                campo_cpf = sel
                break

        if not campo_cpf:
            return resultado_erro(
                "Campo de CPF não localizado na página de consulta.",
                cpf, self.nome_banco
            )

        page.fill(campo_cpf, "")
        page.type(campo_cpf, formatar_cpf(cpf), delay=80)
        _pausa_humana(0.5, 1.0)

        # ── Submissão ─────────────────────────────────────────────────────
        seletores_btn = ["#lnkConsultar", "#btnConsultar", "input[type=submit]", "button:has-text('Consultar')"]
        for sel in seletores_btn:
            if page.locator(sel).count() > 0:
                page.click(sel)
                break
        else:
            page.keyboard.press("Enter")

        # Aguarda resultado — pode ser uma tabela, div ou modal
        try:
            page.wait_for_selector(
                "#gridResultado, .resultado-margem, #tblMargem, #lblMargem",
                timeout=TIMEOUT_CONSULTA
            )
        except Exception:
            # Verifica se retornou mensagem de CPF não encontrado
            conteudo = page.content().lower()
            if "não encontrado" in conteudo or "sem margem" in conteudo:
                return {**resultado_erro("CPF sem margem disponível", cpf, self.nome_banco),
                        "status_consulta": "sem_margem"}
            return resultado_erro("Timeout aguardando resultado de consulta.", cpf, self.nome_banco)

        _pausa_humana(0.5, 1.0)

        # ── Extração dos valores ──────────────────────────────────────────
        def _texto(sel: str) -> Optional[str]:
            loc = page.locator(sel)
            return loc.first.text_content().strip() if loc.count() > 0 else None

        # Tenta extrair status de autorização
        status_autorizacao = _texto("#lblStatus, .status-autorizacao, td:has-text('Status') + td")
        margem_txt   = _texto("#lblMargem, .margem-disponivel, td:has-text('Margem Disponível') + td")
        cartao_txt   = _texto("#lblMargemCartao, .margem-cartao, td:has-text('Margem Cartão') + td")
        nome_txt     = _texto("#lblNome, .nome-titular, td:has-text('Nome') + td")
        orgao_txt    = _texto("#lblOrgao, .orgao, td:has-text('Órgão') + td")

        # Se não achou valores, tenta extrair da tabela genérica
        if not margem_txt:
            cells = page.locator("table tr td").all_text_contents()
            for i, cell in enumerate(cells):
                if "margem" in cell.lower() and i + 1 < len(cells):
                    margem_txt = cells[i + 1]
                    break

        margem_val = _parse_moeda(margem_txt)
        cartao_val = _parse_moeda(cartao_txt)

        # Determina status da consulta
        if status_autorizacao:
            s_lower = status_autorizacao.lower()
            if any(x in s_lower for x in ["autorizado", "aprovado", "ok", "sucesso"]):
                status = "sucesso"
            elif any(x in s_lower for x in ["sem margem", "indisponível", "bloqueado"]):
                status = "sem_margem"
            else:
                status = "sucesso" if margem_val else "sem_margem"
        else:
            status = "sucesso" if (margem_val is not None) else "sem_margem"

        dados_brutos = json.dumps({
            "status_autorizacao": status_autorizacao,
            "url_consulta": page.url,
        }, ensure_ascii=False)

        return {
            "cpf": cpf,
            "status_consulta": status,
            "mensagem_erro": None,
            "nome_titular": nome_txt,
            "margem_disponivel": margem_val,
            "margem_cartao": cartao_val,
            "margem_beneficio": None,
            "banco": self.nome_banco,
            "orgao": orgao_txt,
            "dados_brutos": dados_brutos,
        }


# ── Adaptador: GridSoftware / Roraima ─────────────────────────────────────────

class GridSoftwareAdapter(PlaywrightAdapter):
    """
    Adaptador para o portal GridSoftware (SIGAC-Web — Roraima).

    Fluxo de login:
      1. GET → GRID_URL (página JSF)
      2. Clica em 'Consignatária' (#j_idt15:btnConsignataria) para
         selecionar o tipo de usuário correto
      3. Preenche #username e #password
      4. Resolve reCAPTCHA via 2Captcha e injeta o token
      5. Clica #submit
      6. Aguarda área logada

    Fluxo de consulta:
      - Navega até a tela de consulta de margem
      - Insere o CPF
      - Lê a aba "Margem de Empréstimo" → margem_disponivel
      - Lê a aba "Margem de Cartão"     → margem_cartao
      - Consolida os dois valores no resultado

    Configuração (.env):
      GRID_URL             → URL da página de login
      GRID_LOGIN           → CPF do operador (apenas dígitos)
      GRID_SENHA           → Senha
      TWOCAPTCHA_API_KEY   → Chave da API 2Captcha
    """

    nome_banco = "GridSoftware / Roraima"
    CHAVE_SESSAO = "grid_roraima"
    URL_LOGIN = settings.GRID_URL

    # Seletores da tela de login
    SEL_BTN_CONSIGNATARIA = "#j_idt15\\:btnConsignataria"  # botão de seleção de perfil
    SEL_USUARIO           = "#username"
    SEL_SENHA             = "#password"
    SEL_SUBMIT            = "#submit"
    SEL_RECAPTCHA         = ".g-recaptcha"

    def _esta_logado(self, page) -> bool:
        url = page.url.lower()
        return "login" not in url and ("home" in url or "principal" in url or "sigac" in url)

    def _obter_sitekey_recaptcha(self, page) -> Optional[str]:
        """Extrai o data-sitekey do elemento reCAPTCHA."""
        loc = page.locator(self.SEL_RECAPTCHA)
        if loc.count() == 0:
            # Tenta extrair via iframe do reCAPTCHA
            loc_iframe = page.locator("iframe[src*='recaptcha']")
            if loc_iframe.count() > 0:
                src = loc_iframe.first.get_attribute("src") or ""
                match = re.search(r"k=([A-Za-z0-9_-]+)", src)
                return match.group(1) if match else None
            return None
        return loc.first.get_attribute("data-sitekey")

    def _fazer_login(self, page) -> None:
        logger.info("[GridSoftware] Iniciando login.")

        page.goto(self.URL_LOGIN, wait_until="networkidle", timeout=TIMEOUT_NAVEGACAO)
        _pausa_humana(1, 2)

        # ── Passo 1: selecionar perfil Consignatária ──────────────────────
        btn_sel = self.SEL_BTN_CONSIGNATARIA
        page.wait_for_selector(btn_sel, state="visible", timeout=TIMEOUT_ELEMENTO)
        page.click(btn_sel)
        _pausa_humana(1, 2)

        # Aguarda o formulário de login ser exibido (pode haver reload ou modal)
        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_ELEMENTO)
        logger.info("[GridSoftware] Formulário de login visível.")

        # ── Passo 2: preencher credenciais ────────────────────────────────
        page.fill(self.SEL_USUARIO, "")
        page.type(self.SEL_USUARIO, settings.GRID_LOGIN, delay=random.randint(60, 130))
        _pausa_humana(0.5, 1.0)

        page.fill(self.SEL_SENHA, "")
        page.type(self.SEL_SENHA, settings.GRID_SENHA, delay=random.randint(60, 130))
        _pausa_humana(0.5, 1.0)

        # ── Passo 3: resolver reCAPTCHA ───────────────────────────────────
        sitekey = self._obter_sitekey_recaptcha(page)
        if sitekey:
            logger.info("[GridSoftware] reCAPTCHA detectado. Sitekey: %s", sitekey)
            solver = TwoCaptchaSolver()
            token = solver.resolver(sitekey=sitekey, page_url=page.url)
            TwoCaptchaSolver.injetar_token(page, token)
            _pausa_humana(1.0, 2.0)
        else:
            logger.warning("[GridSoftware] reCAPTCHA não encontrado — prosseguindo sem resolução.")

        # ── Passo 4: submeter formulário ──────────────────────────────────
        page.click(self.SEL_SUBMIT)
        try:
            page.wait_for_url(
                lambda url: "login" not in url.lower(),
                timeout=20_000
            )
        except Exception:
            # Verifica mensagem de erro de login
            erro_sel = ".ui-messages-error, .login-error, #mensagemErro"
            if page.locator(erro_sel).count() > 0:
                msg = page.locator(erro_sel).first.text_content()
                raise RuntimeError(f"Falha no login GridSoftware: {msg}")
            # Pode ser redirecionamento lento
            page.wait_for_load_state("networkidle", timeout=15_000)

        _pausa_humana(1, 2)
        logger.info("[GridSoftware] Login concluído. URL: %s", page.url)

    # ── Navegação interna ─────────────────────────────────────────────────────

    def _navegar_consulta_margem(self, page) -> None:
        """Navega até a tela de consulta de margem consignada."""
        # Tenta menu via seletores conhecidos do GridSoftware
        menus = [
            "a:has-text('Consulta de Margem')",
            "a:has-text('Margem Consignada')",
            "#form\\:menuConsulta",
            ".menu-item:has-text('Margem')",
        ]
        for sel in menus:
            if page.locator(sel).count() > 0:
                page.click(sel)
                page.wait_for_load_state("networkidle", timeout=TIMEOUT_NAVEGACAO)
                _pausa_humana(1, 2)
                return

        logger.warning("[GridSoftware] Menu de consulta não localizado — tentando URL direta.")
        url_consulta = self.URL_LOGIN.replace("login.jsf", "margem/consultaMargem.jsf")
        page.goto(url_consulta, wait_until="networkidle", timeout=TIMEOUT_NAVEGACAO)
        _pausa_humana(1, 2)

    def _inserir_cpf_e_aguardar(self, page, cpf: str) -> bool:
        """Insere CPF no campo, submete e aguarda resultado. Retorna True se achou resultado."""
        seletores_cpf = [
            "#formConsulta\\:cpf",
            "#cpf",
            "input[name*='cpf']",
            "input[placeholder*='CPF']",
        ]
        campo_cpf = None
        for sel in seletores_cpf:
            if page.locator(sel).count() > 0:
                campo_cpf = sel
                break

        if not campo_cpf:
            raise RuntimeError("Campo CPF não encontrado na tela de consulta.")

        page.fill(campo_cpf, "")
        page.type(campo_cpf, formatar_cpf(cpf), delay=80)
        _pausa_humana(0.5, 1.0)

        # Submete
        seletores_btn = [
            "#formConsulta\\:btnConsultar",
            "button:has-text('Consultar')",
            "input[value='Consultar']",
        ]
        for sel in seletores_btn:
            if page.locator(sel).count() > 0:
                page.click(sel)
                break
        else:
            page.keyboard.press("Enter")

        # Aguarda resultado (tabela ou mensagem de erro)
        try:
            page.wait_for_selector(
                "#formResultado, .resultado-margem, .ui-datatable, #tblMargem",
                timeout=TIMEOUT_CONSULTA
            )
            return True
        except Exception:
            return False

    def _ler_aba_emprestimo(self, page) -> Optional[float]:
        """
        Lê o valor de Margem de Empréstimo.
        Navega para a aba correspondente se houver múltiplas abas.
        """
        abas_emprestimo = [
            "a:has-text('Margem de Empréstimo')",
            "li:has-text('Empréstimo') a",
            "#tabEmprestimo",
            ".ui-tabview-nav li:nth-child(1) a",
        ]
        for sel in abas_emprestimo:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click()
                _pausa_humana(0.5, 1.0)
                break

        # Extrai valor
        seletores_valor = [
            "#formResultado\\:margemEmprestimo",
            "td:has-text('Margem Disponível') + td",
            "td:has-text('Margem Empréstimo') + td",
            ".margem-emprestimo-valor",
        ]
        for sel in seletores_valor:
            loc = page.locator(sel)
            if loc.count() > 0:
                return _parse_moeda(loc.first.text_content())
        return None

    def _ler_aba_cartao(self, page) -> Optional[float]:
        """
        Lê o valor de Margem de Cartão.
        Navega para a aba correspondente se houver múltiplas abas.
        """
        abas_cartao = [
            "a:has-text('Margem de Cartão')",
            "a:has-text('Cartão')",
            "#tabCartao",
            ".ui-tabview-nav li:nth-child(2) a",
        ]
        for sel in abas_cartao:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click()
                _pausa_humana(0.5, 1.0)
                break

        # Extrai valor
        seletores_valor = [
            "#formResultado\\:margemCartao",
            "td:has-text('Margem Cartão') + td",
            "td:has-text('Cartão de Crédito') + td",
            ".margem-cartao-valor",
        ]
        for sel in seletores_valor:
            loc = page.locator(sel)
            if loc.count() > 0:
                return _parse_moeda(loc.first.text_content())
        return None

    def _extrair_margem(self, page, cpf: str) -> dict:
        """Fluxo completo de consulta de margem no GridSoftware."""
        self._navegar_consulta_margem(page)

        achou = self._inserir_cpf_e_aguardar(page, cpf)
        if not achou:
            conteudo = page.content().lower()
            if "não encontrado" in conteudo or "sem margem" in conteudo or "não possui" in conteudo:
                return {**resultado_erro("Servidor sem margem disponível", cpf, self.nome_banco),
                        "status_consulta": "sem_margem"}
            return resultado_erro("Resultado não carregou no tempo esperado.", cpf, self.nome_banco)

        _pausa_humana(0.5, 1.0)

        # ── Extrair nome e órgão ──────────────────────────────────────────
        def _texto(sels: list) -> Optional[str]:
            for sel in sels:
                loc = page.locator(sel)
                if loc.count() > 0:
                    t = loc.first.text_content()
                    if t:
                        return t.strip()
            return None

        nome_txt = _texto([
            "#formResultado\\:nome",
            "td:has-text('Nome') + td",
            ".nome-servidor",
        ])
        orgao_txt = _texto([
            "#formResultado\\:orgao",
            "td:has-text('Órgão') + td",
            ".orgao-servidor",
        ])

        # ── Ler abas de margem ────────────────────────────────────────────
        margem_emprestimo = self._ler_aba_emprestimo(page)
        margem_cartao     = self._ler_aba_cartao(page)

        status = "sucesso" if (margem_emprestimo is not None or margem_cartao is not None) else "sem_margem"

        dados_brutos = json.dumps({
            "margem_emprestimo_raw": str(margem_emprestimo),
            "margem_cartao_raw": str(margem_cartao),
            "url_consulta": page.url,
        }, ensure_ascii=False)

        logger.info(
            "[GridSoftware] CPF %s → Empréstimo: R$ %s | Cartão: R$ %s",
            cpf, margem_emprestimo, margem_cartao
        )

        return {
            "cpf": cpf,
            "status_consulta": status,
            "mensagem_erro": None,
            "nome_titular": nome_txt,
            "margem_disponivel": margem_emprestimo,
            "margem_cartao": margem_cartao,
            "margem_beneficio": None,
            "banco": self.nome_banco,
            "orgao": orgao_txt,
            "dados_brutos": dados_brutos,
        }


# ── Adaptadores esqueleto (BB / CEF) ──────────────────────────────────────────

class BancoBrasilAdapter(PlaywrightAdapter):
    nome_banco = "Banco do Brasil"
    CHAVE_SESSAO = "banco_brasil"
    URL_LOGIN = "https://portal.bb.com.br/login"

    def _fazer_login(self, page) -> None:
        page.goto(self.URL_LOGIN, wait_until="networkidle")
        page.fill("#usuario", settings.AKICAPITAL_LOGIN)
        page.fill("#senha", settings.AKICAPITAL_SENHA)
        page.click("button[type=submit]")
        page.wait_for_selector("#dashboard", timeout=15_000)

    def _extrair_margem(self, page, cpf: str) -> dict:
        return resultado_erro("Adaptador BB não implementado.", cpf, self.nome_banco)


class CEFAdapter(PlaywrightAdapter):
    nome_banco = "Caixa Econômica Federal"
    CHAVE_SESSAO = "cef"
    URL_LOGIN = "https://habitacao.caixa.gov.br/login"

    def _fazer_login(self, page) -> None:
        page.goto(self.URL_LOGIN, wait_until="networkidle")
        page.fill("input[name='usuario']", settings.AKICAPITAL_LOGIN)
        page.fill("input[name='senha']", settings.AKICAPITAL_SENHA)
        page.click("button.btn-login")
        page.wait_for_url("**/home**", timeout=15_000)

    def _extrair_margem(self, page, cpf: str) -> dict:
        return resultado_erro("Adaptador CEF não implementado.", cpf, self.nome_banco)


# ── Simulador ─────────────────────────────────────────────────────────────────

class PortalExemploAdapter(BaseAdapter):
    """Adaptador simulado — para testes sem credenciais de portal real."""

    nome_banco = "Portal Exemplo (Simulado)"

    def consultar(self, cpf: str) -> dict:
        cpf_limpo = limpar_cpf(cpf)
        if not validar_cpf(cpf_limpo):
            return {**resultado_erro("CPF inválido", cpf_limpo, self.nome_banco),
                    "status_consulta": "cpf_invalido"}

        _pausa_humana(0.5, 1.5)
        sorteio = random.random()
        if sorteio < 0.10:
            return resultado_erro("Timeout simulado", cpf_limpo, self.nome_banco)
        if sorteio < 0.15:
            return {**resultado_erro("Sem margem simulado", cpf_limpo, self.nome_banco),
                    "status_consulta": "sem_margem"}

        margem = round(random.uniform(100, 3500), 2)
        return {
            "cpf": cpf_limpo,
            "status_consulta": "sucesso",
            "mensagem_erro": None,
            "nome_titular": f"TITULAR DO CPF {cpf_limpo[-4:]}",
            "margem_disponivel": margem,
            "margem_cartao": round(margem * 0.3, 2),
            "margem_beneficio": round(random.uniform(500, 5000), 2),
            "banco": self.nome_banco,
            "orgao": "INSS" if random.random() > 0.5 else "SIAPE",
            "dados_brutos": json.dumps({"competencia": "04/2026", "especie": "41"}),
        }


# ── Fábrica de adaptadores ────────────────────────────────────────────────────

ADAPTADORES: dict[str, type] = {
    "exemplo":  PortalExemploAdapter,
    "aki":      AkiCapitalAdapter,
    "grid":     GridSoftwareAdapter,
    "bb":       BancoBrasilAdapter,
    "cef":      CEFAdapter,
}


def get_adapter(banco: str = "exemplo") -> BaseAdapter:
    cls = ADAPTADORES.get(banco, PortalExemploAdapter)
    return cls()


# ── Função pública ────────────────────────────────────────────────────────────

def consultar_margem(cpf: str, banco: str = "exemplo") -> dict:
    """
    Ponto de entrada chamado pelo worker Celery.

    Args:
        cpf:   CPF com ou sem formatação.
        banco: Chave do adaptador — exemplo | aki | grid | bb | cef

    Returns:
        dict: cpf, status_consulta, margem_disponivel, margem_cartao,
              margem_beneficio, nome_titular, banco, orgao,
              mensagem_erro, dados_brutos
    """
    adapter = get_adapter(banco)
    logger.info("Consultando CPF %s via '%s' (%s)", cpf, banco, adapter.nome_banco)
    return adapter.consultar(cpf)
