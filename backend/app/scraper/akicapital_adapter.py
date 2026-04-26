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

    def __init__(self, credencial: Optional[dict] = None):
        super().__init__(credencial)
        # URL pode ser sobrescrita pela credencial do usuário
        self.URL_LOGIN = (
            (credencial or {}).get("url")
            or self._URL_LOGIN_DEFAULT
        )

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

    # ── Navegação para consulta ───────────────────────────────────────────────

    def _navegar_para_consulta(self, page) -> None:
        # Tenta via menu primeiro (links renderizados pelo JS)
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
            page.wait_for_load_state("domcontentloaded", timeout=TIMEOUT_NAV)
            pausa_humana(1.0, 2.0)
            return

        # Extrai FISession da URL atual — o WebAutorizador exige esse parâmetro
        fi_session = ""
        fi_match = re.search(r"[Ff][Ii][Ss]ession=([^&\s]+)", page.url)
        if fi_match:
            fi_session = fi_match.group(1)
            logger.info("[AkiCapital] FISession capturado: %s…", fi_session[:8])

        base = re.sub(r"/Login/.*", "", self.URL_LOGIN.split("?")[0])

        # Tenta primeiro com FISession (requerido pelo portal), depois sem
        urls_tentativas: list[str] = []
        if fi_session:
            urls_tentativas.append(
                f"{base}/Consulta/ConsultaMargem.aspx?FISession={fi_session}"
            )
        urls_tentativas.append(f"{base}/Consulta/ConsultaMargem.aspx")

        for url_consulta in urls_tentativas:
            logger.info("[AkiCapital] Tentando página de consulta: %s", url_consulta)
            try:
                page.goto(url_consulta, wait_until="domcontentloaded", timeout=TIMEOUT_NAV)
                pausa_humana(1.0, 2.0)
                if "login" not in page.url.lower():
                    logger.info("[AkiCapital] Página de consulta carregada: %s", page.url)
                    return
                logger.warning("[AkiCapital] Redirecionado para login após navegar para consulta.")
            except Exception as exc:
                logger.warning("[AkiCapital] Falha ao navegar para %s: %s", url_consulta, exc)

        logger.error("[AkiCapital] Não foi possível alcançar a página de consulta de margem.")

    # ── Extração ──────────────────────────────────────────────────────────────

    def _extrair_margem(self, page, cpf: str) -> dict:
        self._navegar_para_consulta(page)

        campo_cpf = self._primeiro_seletor(page, self.SEL_CAMPO_CPF)
        if not campo_cpf:
            return resultado_erro(
                "Campo CPF não encontrado na página de consulta.", cpf, self.NOME_BANCO
            )

        page.fill(campo_cpf, "")
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
                "não encontrado", "sem margem", "não possui",
                "cpf não", "nenhum registro",
            ]):
                return resultado_sem_margem(cpf, self.NOME_BANCO)
            return resultado_erro(
                "Timeout aguardando resultado de consulta.", cpf, self.NOME_BANCO
            )

        pausa_humana(0.5, 1.0)

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
