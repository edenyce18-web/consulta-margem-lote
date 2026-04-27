"""
scraper/akicapital_adapter.py
──────────────────────────────
Adaptador para o portal AkiCapital (WebAutorizador ASP.NET).

Suporte a credenciais dinâmicas por usuário:
    adapter = AkiCapitalAdapter(credencial={"login": "...", "senha": "...", "url": "..."})
"""

from __future__ import annotations

import json
import logging
import re
import random
from typing import Optional

from app.config import settings
from app.scraper.base_adapter import (
    BaseScraperAdapter,
    TIMEOUT_NAV, TIMEOUT_EL, TIMEOUT_CONS,
)
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    formatar_cpf, pausa_humana, digitar_lento,
    parse_moeda, resultado_erro, resultado_sem_margem, clicar_seguro,
    salvar_screenshot,
)
from pathlib import Path

logger = logging.getLogger(__name__)


@AdapterManager.registrar("aki")
class AkiCapitalAdapter(BaseScraperAdapter):
    """Adaptador para o portal AkiCapital / WebAutorizador ASP.NET."""

    NOME_BANCO   = "AkiCapital"
    CHAVE_SESSAO = "akicapital"

    # URL padrão (pode ser sobrescrita pela credencial do usuário)
    _URL_LOGIN_DEFAULT = settings.AKICAPITAL_URL

    # ── Seletores ─────────────────────────────────────────────────────────────
    SEL_USUARIO = "#EUsuario_CAMPO"
    SEL_SENHA   = "#ESenha_CAMPO"
    SEL_ENTRAR  = "#lnkEntrar"

    SEL_AREA_LOGADA = [
        "#lnkSair", "#lnkLogout", ".menu-principal",
        "#divMenuTopo", "[id*='LogOff']", "[id*='Logout']",
    ]
    SEL_CAMPO_CPF = [
        "#ECPF_CAMPO", "#txtCPF", "input[id*='CPF']",
        "input[name*='cpf']", "input[placeholder*='CPF']",
    ]
    SEL_BTN_CONSULTAR = [
        "#lnkConsultar", "#btnConsultar", "#lnkPesquisar",
        "input[type='submit'][value*='Consultar']",
        "a[id*='Consultar']", "button:has-text('Consultar')",
    ]
    SEL_RESULTADO = [
        "td:has-text('EMPRÉSTIMO BANCOS PRIVADOS')",
        "td:has-text('CARTÃO DE CRÉDITO')",
        "td:has-text('CARTÃO BENEFÍCIO')",
        "td:has-text('Empréstimo Bancos Privados')",
        "#GridResultados", "#tblMargem", "#divResultado", "table[id*='Grid']",
    ]
    # Botões que resetam o formulário sem recarregar a página inteira
    SEL_NOVA_CONSULTA = [
        "#lnkNovaPesquisa", "#lnkNovaPesquisa2", "#lnkNova", "#lnkLimpar",
        "#btnLimpar", "#btnNovaPesquisa", "#lnkVoltar",
        "a:has-text('Nova Pesquisa')", "a:has-text('Nova Consulta')",
        "a:has-text('Limpar')", "a:has-text('Voltar')",
        "input[value='Limpar']", "input[value='Nova Consulta']",
        "button:has-text('Limpar')", "button:has-text('Nova Consulta')",
    ]

    def __init__(self, credencial: Optional[dict] = None, usuario_id: Optional[str] = None):
        super().__init__(credencial, usuario_id=usuario_id)
        # URL pode ser sobrescrita pela credencial do usuário
        self.URL_LOGIN = (
            (credencial or {}).get("url")
            or self._URL_LOGIN_DEFAULT
        )
        # T1: FISession salvo após login para reutilizar em _navegar_para_consulta
        self._fi_session: str = ""

    @property
    def _login(self) -> str:
        return self._credencial.get("login") or settings.AKICAPITAL_LOGIN

    @property
    def _senha(self) -> str:
        return self._credencial.get("senha") or settings.AKICAPITAL_SENHA

    # ── Verificação de sessão ─────────────────────────────────────────────────

    def _esta_logado(self, page) -> bool:
        url = page.url.lower()
        if "login" in url:
            return False
        # FISession na URL indica sessão autenticada no WebAutorizador
        if "fisession=" in url:
            return True
        # T2: páginas de erro internas do portal (Erro.aspx) não indicam logout —
        # a sessão ainda é válida; evita re-login desnecessário entre CPFs
        if "erro.aspx" in url or "error.aspx" in url or "/erro" in url:
            return True
        return self._primeiro_seletor(page, self.SEL_AREA_LOGADA) is not None

    # ── Autenticação ──────────────────────────────────────────────────────────

    def _fazer_login(self, page) -> None:
        logger.info("[AkiCapital] Navegando para tela de login.")
        page.goto(self.URL_LOGIN, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
        pausa_humana(1.0, 2.0)

        page.wait_for_selector(self.SEL_USUARIO, state="visible", timeout=TIMEOUT_EL)

        page.click(self.SEL_USUARIO)
        digitar_lento(page, self.SEL_USUARIO, self._login)
        pausa_humana(0.5, 1.0)

        page.click(self.SEL_SENHA)
        digitar_lento(page, self.SEL_SENHA, self._senha)
        pausa_humana(0.5, 1.2)

        page.click(self.SEL_ENTRAR)
        logger.info("[AkiCapital] Aguardando redirecionamento pós-login...")

        try:
            page.wait_for_function(
                "() => !window.location.href.toLowerCase().includes('login')",
                timeout=30_000,
            )
        except Exception:
            # Captura URL e texto da página para diagnóstico
            url_atual = page.url
            logger.warning("[AkiCapital] Timeout pós-login. URL atual: %s", url_atual)

            sel = self._primeiro_seletor(page, self.SEL_AREA_LOGADA)
            if sel:
                # Encontrou área logada mesmo com URL contendo 'login'
                pass
            else:
                erro_txt = self._texto_seletor(page, [
                    ".MensagemErro", "#lblErro", "#lblMensagem",
                    ".alert-danger", ".alert-error",
                    "[class*='erro']", "[class*='error']", "[class*='Erro']",
                    "span[id*='Erro']", "span[id*='Mensagem']",
                    ".validation-summary-errors",
                ])
                # Tenta pegar qualquer texto de alerta visível
                if not erro_txt:
                    try:
                        erro_txt = page.locator("text=/senha|inválid|incorret|bloqueado|expirado/i").first.text_content(timeout=2000)
                    except Exception:
                        pass
                raise RuntimeError(
                    f"Login falhou (URL: {url_atual}). "
                    f"Verifique login/senha da credencial. "
                    f"Mensagem do portal: {erro_txt or 'sem detalhes'}"
                )

        pausa_humana(1.0, 2.0)
        logger.info("[AkiCapital] Login concluído. URL atual: %s", page.url)

        # T1: captura FISession após login para reutilizar na navegação
        fi_match = re.search(r"[Ff][Ii][Ss]ession=([^&\s]+)", page.url)
        if fi_match:
            self._fi_session = fi_match.group(1)
            logger.info("[AkiCapital] FISession salvo: %s…", self._fi_session[:8])

    # ── Navegação para consulta ───────────────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        """
        Navega para a página de consulta de margem.

        Estratégia (T3 — corrigida):
          1. Volta à página principal autenticada (/?FISession=...) para garantir
             que o menu esteja disponível no DOM.
          2. Clica no item de menu via JS (ignora visibilidade CSS) com _clicar_com_fallback.
          3. Fallback: tenta ConsultaMargem.aspx?FISession=... apenas como último recurso.

        NOTA: Navegação direta para ConsultaMargem.aspx redireciona para Erro.aspx
        neste portal — o WebAutorizador exige fluxo via menu a partir da home.
        """
        # T3: usa FISession salvo no login (T1) ou extrai da URL atual como fallback
        fi_session = self._fi_session
        if not fi_session:
            fi_match = re.search(r"[Ff][Ii][Ss]ession=([^&\s]+)", page.url)
            if fi_match:
                fi_session = fi_match.group(1)
                self._fi_session = fi_session
                logger.info("[AkiCapital] FISession capturado da URL: %s…", fi_session[:8])

        base = re.sub(r"/Login/.*", "", self.URL_LOGIN.split("?")[0]).split("?")[0]

        # Estratégia 1: volta à home autenticada para que o menu esteja no DOM
        if fi_session:
            home_url = f"{base}/?FISession={fi_session}"
            logger.info("[AkiCapital] Voltando à home autenticada: %s", home_url)
            try:
                page.goto(home_url, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
                pausa_humana(0.5, 1.2)
            except Exception as exc:
                logger.warning("[AkiCapital] Falha ao acessar home: %s", exc)

        # Estratégia 2: clique no menu (DOM — ignora visibilidade CSS)
        sels_menu = [
            "a[href*='ConsultaMargem']",
            "a[href*='Margem']",
            "#mnuConsultaMargem",
            "a:has-text('Consulta de Margem')",
            "a:has-text('Margem Consignada')",
            "a:has-text('Consultar')",
        ]
        sel_menu = self._primeiro_seletor(page, sels_menu, exigir_visivel=False)
        if sel_menu:
            logger.info("[AkiCapital] Clicando no menu via JS: %s", sel_menu)
            clicou = self._clicar_com_fallback(page, sel_menu, timeout=8_000)
            if clicou:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15_000)
                except Exception:
                    pass
                pausa_humana(0.5, 1.5)
                if "login" not in page.url.lower():
                    logger.info("[AkiCapital] Página de consulta via menu: %s", page.url)
                    return
                logger.warning("[AkiCapital] Menu clicado mas sessão expirou.")

        # Estratégia 3 (último recurso): URL direta — pode redirecionar para Erro.aspx
        if fi_session:
            url_fallback = f"{base}/Consulta/ConsultaMargem.aspx?FISession={fi_session}"
            logger.warning("[AkiCapital] Fallback URL direta: %s", url_fallback)
            try:
                page.goto(url_fallback, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
                pausa_humana(0.5, 1.2)
                if "login" not in page.url.lower():
                    return
            except Exception as exc:
                logger.warning("[AkiCapital] Fallback URL falhou: %s", exc)

        logger.error("[AkiCapital] Não foi possível alcançar a página de consulta de margem.")

    # ── Helpers de navegação rápida ───────────────────────────────────────────

    def _tentar_nova_consulta(self, page) -> None:
        """
        Reseta o formulário clicando em 'Nova Pesquisa'/'Limpar' se disponível.
        Muito mais rápido do que navegar de volta para a home (evita 2 page loads).
        """
        sel = self._primeiro_seletor(page, self.SEL_NOVA_CONSULTA)
        if sel:
            try:
                self._clicar_com_fallback(page, sel, timeout=5_000)
                pausa_humana(0.2, 0.5)
                logger.debug("[AkiCapital] Formulário resetado via '%s'", sel)
            except Exception as exc:
                logger.debug("[AkiCapital] Falha ao clicar em Nova Consulta: %s", exc)

    def _preencher_cpf_rapido(self, page, campo_cpf: str, cpf_formatado: str) -> None:
        """
        Preenche o campo CPF de forma rápida: triple-click para selecionar tudo,
        depois digita. Evita o delay de 60-130ms/char do digitar_lento.
        Cai em digitar_lento como fallback se falhar.
        """
        try:
            loc = page.locator(campo_cpf).first
            loc.triple_click(timeout=3_000)
            loc.type(cpf_formatado, delay=random.randint(30, 60))
        except Exception:
            try:
                digitar_lento(page, campo_cpf, cpf_formatado)
            except Exception as exc:
                logger.warning("[AkiCapital] Falha ao preencher CPF: %s", exc)

    # ── Extração ──────────────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        # ── Otimização principal ──────────────────────────────────────────────
        # Verifica se o campo CPF já está na página ANTES de navegar.
        # Para lotes: após o 1º CPF a página de consulta permanece aberta;
        # navegar de volta para a home e clicar no menu a cada CPF desperdiça
        # ~6-10s por CPF. Se o campo já estiver visível, apenas reseta o form.
        campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF, exigir_visivel=False)

        if campo_cpf:
            logger.debug("[AkiCapital] Campo CPF já visível — pulando navegação para CPF %s", cpf)
            self._tentar_nova_consulta(page)
            # Reconfirma que o campo ainda está lá após o reset
            campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF, exigir_visivel=False)
        else:
            # Campo não encontrado — precisa navegar para a página de consulta
            self._navegar_para_consulta(page)
            campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF, exigir_visivel=False)

        if not campo_cpf:
            # Salva screenshot para diagnóstico (informa qual URL estava)
            try:
                salvar_screenshot(page, "aki_sem_campo_cpf", Path("/tmp/pw_sessions"))
            except Exception:
                pass
            logger.error("[AkiCapital] Campo CPF não encontrado. URL atual: %s", page.url)
            return resultado_erro(
                f"Campo CPF não encontrado na página de consulta (URL: {page.url}).",
                cpf, self.NOME_BANCO
            )

        # ── Preenche CPF ──────────────────────────────────────────────────────
        cpf_formatado = formatar_cpf(cpf)
        self._preencher_cpf_rapido(page, campo_cpf, cpf_formatado)
        pausa_humana(0.1, 0.3)

        # ── Clica em Consultar com cadeia de fallbacks ────────────────────────
        btn = self._primeiro_seletor(page, self.SEL_BTN_CONSULTAR, exigir_visivel=False)
        clicou = False
        if btn:
            clicou = self._clicar_com_fallback(page, btn, timeout=8_000)
        if not clicou:
            logger.warning("[AkiCapital] Botão Consultar não clicável — usando Enter.")
            try:
                page.locator(campo_cpf).first.press("Enter")
                clicou = True
            except Exception:
                page.keyboard.press("Enter")
                clicou = True

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

        pausa_humana(0.2, 0.5)

        nome_txt     = self._extrair_celula_apos(page, "Nome")
        orgao_txt    = self._extrair_celula_apos(page, "Órgão")
        vinculo_txt  = self._extrair_celula_apos(page, "Tipo Vínculo")
        matricula_txt = self._extrair_celula_apos(page, "Matrícula")

        emp_sit = self._situacao_produto(page, "Empréstimo")
        cc_sit  = self._situacao_produto(page, "Cartão de Crédito")
        cb_sit  = self._situacao_produto(page, "Cartão de Benefício")

        margem_beneficio = self._extrair_margem_beneficio(page)

        autorizados = [s for s in [emp_sit, cc_sit, cb_sit]
                       if s and "autorizado" in s.lower() and "não" not in s.lower()]
        status = "sucesso" if (autorizados or margem_beneficio) else "sem_margem"

        return {
            "cpf":             cpf,
            "status_consulta": status,
            "mensagem_erro":   None,
            "nome_titular":    nome_txt,
            "orgao":           orgao_txt,
            "tipo_vinculo":    vinculo_txt,
            "matricula":       matricula_txt,
            "margem_disponivel": None,
            "margem_cartao":     None,
            "margem_beneficio":  margem_beneficio,
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
        try:
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
