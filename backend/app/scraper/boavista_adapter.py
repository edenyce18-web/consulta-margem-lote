from __future__ import annotations

from playwright.sync_api import TimeoutError as PWTimeout

from app.config import settings
from app.scraper.base_adapter import BaseScraperAdapter, TIMEOUT_EL
from app.scraper.manager import AdapterManager
from app.scraper.utils import (
    clicar_seguro,
    digitar_lento,
    formatar_cpf,
    parse_moeda,
    pausa_humana,
    resultado_erro,
)


@AdapterManager.registrar("boavista")
class BoaVistaPrefeituraAdapter(BaseScraperAdapter):
    """Adaptador RF1 Consig para consulta de margem por CPF + órgão."""

    NOME_BANCO = "Prefeitura Boa Vista"
    CHAVE_SESSAO = "boavista_prefeitura"
    URL_LOGIN = "https://boavista.rf1consig.com.br/SGConsignataria/ConsigAcessoUsuarioLogar.aspx"

    def __init__(self, credencial=None, usuario_id=None):
        super().__init__(credencial=credencial, usuario_id=usuario_id)
        self.URL_LOGIN = self._credencial.get("url") or settings.BOAVISTA_URL or self.URL_LOGIN
        self._usuario = self._credencial.get("login") or settings.BOAVISTA_LOGIN
        self._senha = self._credencial.get("senha") or settings.BOAVISTA_SENHA
        self._orgao = self._credencial.get("orgao") or settings.BOAVISTA_ORGAO
        self._codigo_seg = self._credencial.get("codigo_seguranca") or settings.BOAVISTA_CODIGO_SEGURANCA

    def _esta_logado(self, page) -> bool:
        if "ConsigAcessoUsuarioLogar" in page.url:
            return False
        return page.locator("text=Menu do Sistema, text=Dados do Servidor").count() > 0

    def _fazer_login(self, page) -> None:
        if not self._usuario or not self._senha:
            raise RuntimeError("Credenciais ausentes para o portal Boa Vista.")

        page.goto(self.URL_LOGIN, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        digitar_lento(page, "#txtLogin", self._usuario)
        digitar_lento(page, "#txtSenha", self._senha)

        # O portal exibe código de segurança em imagem. Preencher via variável
        # BOAVISTA_CODIGO_SEGURANCA (ou credencial.codigo_seguranca) e manter rotação manual.
        if self._codigo_seg:
            digitar_lento(page, "#txtCodSeguranca", self._codigo_seg)

        clicar_seguro(page, "#btnEntrar, button:has-text('Entrar')")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1200)

        if not self._esta_logado(page):
            raise RuntimeError(
                "Falha no login RF1. Verifique usuário/senha/código de segurança e sessão."
            )

    def _extrair_margem(self, page, cpf: str) -> dict:
        cpf_fmt = formatar_cpf(cpf)

        # Página de consulta do servidor
        try:
            page.goto(
                "https://boavista.rf1consig.com.br/SGConsignataria/GESTOR/CADPessoalListar.aspx",
                wait_until="domcontentloaded",
                timeout=TIMEOUT_EL,
            )
            page.wait_for_timeout(800)
        except PWTimeout:
            return resultado_erro("Timeout ao abrir tela de consulta do servidor", cpf, self.NOME_BANCO)

        # No RF1, CPF + órgão já retornam os dados e a margem.
        page.fill("#txtCPF", cpf_fmt)

        if self._orgao:
            page.select_option("#ddlOrgao", label=self._orgao)
        else:
            # fallback: primeira opção válida (não vazia)
            opcoes = page.locator("#ddlOrgao option").all()
            valor = None
            for op in opcoes:
                v = (op.get_attribute("value") or "").strip()
                if v:
                    valor = v
                    break
            if valor:
                page.select_option("#ddlOrgao", value=valor)
            else:
                return resultado_erro("Órgão não configurado e sem opções disponíveis", cpf, self.NOME_BANCO)

        pausa_humana(0.3, 0.8)
        clicar_seguro(page, "#btnConsultar, button:has-text('Consultar')")
        page.wait_for_timeout(1500)

        def _txt(sel: str) -> str:
            try:
                return page.locator(sel).first.inner_text(timeout=TIMEOUT_EL).strip()
            except Exception:
                return ""

        nome = _txt("#lblNomeServidor, span:has-text('Nome do Servidor') + span")
        orgao = _txt("#lblOrgao, span:has-text('Órgão') + span") or self._orgao
        matricula = _txt("#lblMatricula, span:has-text('Matrícula') + span")

        margem_disp_txt = _txt("#lblMargemConsignavelAtual, td:has-text('Margem Consignável Atual') + td")
        margem_cartao_txt = _txt("#lblMargemCartaoConsignado, td:has-text('Margem Cartão Consignado') + td")
        margem_reservada_txt = _txt("#lblMargemReservada, td:has-text('Margem Reservada') + td")

        margem_disp = parse_moeda(margem_disp_txt)
        margem_cartao = parse_moeda(margem_cartao_txt)
        margem_reservada = parse_moeda(margem_reservada_txt)

        if nome == "" and margem_disp is None and margem_cartao is None and margem_reservada is None:
            return resultado_erro("CPF não retornou dados no RF1 para o órgão informado", cpf, self.NOME_BANCO)

        return {
            "cpf": cpf,
            "nome_titular": nome or None,
            "orgao": orgao or None,
            "matricula": matricula or None,
            "margem_disponivel": margem_disp,
            "margem_cartao": margem_cartao,
            "margem_beneficio": margem_reservada,
            "banco": self.NOME_BANCO,
            "status_consulta": "sucesso",
            "mensagem_erro": None,
            "dados_brutos": {
                "margem_consultada_em_rf1": True,
                "margem_reservada_texto": margem_reservada_txt or None,
            },
        }
