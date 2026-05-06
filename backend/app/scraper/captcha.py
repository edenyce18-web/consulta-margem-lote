"""
scraper/captcha.py
──────────────────
Integração com a API do 2Captcha para resolução automática de reCAPTCHA v2.

Fluxo:
  1. Localiza o sitekey do reCAPTCHA na página
  2. Envia tarefa para a API do 2Captcha
  3. Faz polling até receber o token resolvido
  4. Injeta o token nos campos ocultos da página
  5. Dispara o callback do Google para habilitar o submit

Configuração:
  TWOCAPTCHA_API_KEY       → chave obtida em 2captcha.com
  TWOCAPTCHA_TIMEOUT_S     → tempo máximo de espera (padrão: 120s)
  TWOCAPTCHA_POLL_INTERVAL_S → intervalo entre checks (padrão: 5s)
"""

from __future__ import annotations

import re
import time
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Endpoints da API do 2Captcha
_URL_SUBMIT = "https://2captcha.com/in.php"
_URL_RESULT = "https://2captcha.com/res.php"


class NoCaptchaError(Exception):
    """Levantado quando o reCAPTCHA não é encontrado na página."""


class CaptchaUnsolvableError(Exception):
    """Levantado quando o 2Captcha não consegue resolver o desafio."""


class CaptchaTimeoutError(Exception):
    """Levantado quando o timeout de resolução é excedido."""


class TwoCaptchaSolver:
    """
    Resolver de reCAPTCHA v2 via API do 2Captcha.

    Exemplo de uso:
        solver = TwoCaptchaSolver()
        sitekey = solver.extrair_sitekey(page)
        token   = solver.resolver(sitekey=sitekey, page_url=page.url)
        solver.injetar_token(page, token)
    """

    def __init__(self) -> None:
        self.api_key = settings.TWOCAPTCHA_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "TWOCAPTCHA_API_KEY não configurada. "
                "Adicione ao .env para usar portais com reCAPTCHA."
            )

    # ── Localização do sitekey ────────────────────────────────────────────────

    def extrair_sitekey(self, page) -> Optional[str]:
        """
        Tenta extrair o data-sitekey do reCAPTCHA de três maneiras:
          1. Atributo data-sitekey em .g-recaptcha
          2. Parâmetro k= no src do iframe do reCAPTCHA
          3. Busca via regex no HTML da página
        """
        # Tentativa 1: elemento .g-recaptcha com data-sitekey
        loc = page.locator(".g-recaptcha[data-sitekey]")
        if loc.count() > 0:
            sitekey = loc.first.get_attribute("data-sitekey")
            if sitekey:
                logger.debug("Sitekey encontrado via .g-recaptcha: %s", sitekey)
                return sitekey

        # Tentativa 2: iframe do reCAPTCHA
        loc_iframe = page.locator("iframe[src*='recaptcha/api2']")
        if loc_iframe.count() > 0:
            src = loc_iframe.first.get_attribute("src") or ""
            match = re.search(r"[?&]k=([A-Za-z0-9_-]+)", src)
            if match:
                logger.debug("Sitekey encontrado via iframe: %s", match.group(1))
                return match.group(1)

        # Tentativa 3: regex no HTML bruto
        html = page.content()
        match = re.search(r"['\"]sitekey['\"]\s*:\s*['\"]([A-Za-z0-9_-]{20,})['\"]", html)
        if match:
            logger.debug("Sitekey encontrado via HTML regex: %s", match.group(1))
            return match.group(1)

        logger.warning("Nenhum sitekey reCAPTCHA encontrado na página.")
        return None

    # ── Resolução via API ─────────────────────────────────────────────────────

    def resolver(self, sitekey: str, page_url: str) -> str:
        """
        Envia o desafio ao 2Captcha e aguarda a solução.

        Args:
            sitekey:  data-sitekey do elemento reCAPTCHA.
            page_url: URL completa da página onde o reCAPTCHA aparece.

        Returns:
            Token g-recaptcha-response para injeção.

        Raises:
            CaptchaUnsolvableError: se o 2Captcha não conseguir resolver.
            CaptchaTimeoutError:    se o timeout for atingido.
        """
        logger.info("Submetendo reCAPTCHA ao 2Captcha | sitekey: %.20s...", sitekey)

        # ── 1. Submeter tarefa ────────────────────────────────────────────────
        with httpx.Client(timeout=30) as client:
            resp = client.post(_URL_SUBMIT, data={
                "key":       self.api_key,
                "method":    "userrecaptcha",
                "googlekey": sitekey,
                "pageurl":   page_url,
                "json":      1,
            })
            resp.raise_for_status()
            dados_submit = resp.json()

        if dados_submit.get("status") != 1:
            raise RuntimeError(
                f"2Captcha recusou a tarefa: {dados_submit.get('request', dados_submit)}"
            )

        captcha_id = dados_submit["request"]
        logger.info("Tarefa 2Captcha criada | ID: %s | aguardando solução...", captcha_id)

        # ── 2. Aguardar solução com polling ───────────────────────────────────
        # Aguarda 15s antes do primeiro poll (processamento inicial)
        time.sleep(15)

        deadline = time.time() + settings.TWOCAPTCHA_TIMEOUT_S
        while time.time() < deadline:
            with httpx.Client(timeout=30) as client:
                resp = client.get(_URL_RESULT, params={
                    "key":    self.api_key,
                    "action": "get",
                    "id":     captcha_id,
                    "json":   1,
                })
                resp.raise_for_status()
                dados_result = resp.json()

            request_val = dados_result.get("request", "")

            if dados_result.get("status") == 1:
                logger.info("reCAPTCHA resolvido pelo 2Captcha | ID: %s", captcha_id)
                return request_val  # token JWT

            if request_val == "ERROR_CAPTCHA_UNSOLVABLE":
                raise CaptchaUnsolvableError(
                    "2Captcha não conseguiu resolver o reCAPTCHA. "
                    "Tente novamente ou verifique o sitekey."
                )

            if request_val.startswith("ERROR_"):
                raise RuntimeError(f"Erro 2Captcha: {request_val}")

            logger.debug(
                "2Captcha ainda processando... próximo check em %ds",
                settings.TWOCAPTCHA_POLL_INTERVAL_S,
            )
            time.sleep(settings.TWOCAPTCHA_POLL_INTERVAL_S)

        raise CaptchaTimeoutError(
            f"Timeout: 2Captcha não resolveu em {settings.TWOCAPTCHA_TIMEOUT_S}s."
        )

    # ── Injeção na página ─────────────────────────────────────────────────────

    @staticmethod
    def injetar_token(page, token: str) -> None:
        """
        Injeta o token resolvido no campo oculto g-recaptcha-response
        e dispara o callback do Google para habilitar o botão de submit.

        Compatível com reCAPTCHA v2 (checkbox e invisible).
        """
        # Injeta no campo oculto padrão do reCAPTCHA
        page.evaluate(f"""
            (() => {{
                const responseField = document.getElementById('g-recaptcha-response');
                if (responseField) {{
                    responseField.innerHTML = '{token}';
                    responseField.style.display = 'block';
                }}

                // Tenta disparar callbacks registrados pelo reCAPTCHA
                try {{
                    const clients = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients;
                    if (clients) {{
                        Object.values(clients).forEach(client => {{
                            const entries = Object.entries(client);
                            const callbackEntry = entries.find(
                                ([k, v]) => v && typeof v.callback === 'function'
                            );
                            if (callbackEntry) callbackEntry[1].callback('{token}');
                        }});
                    }}
                }} catch(e) {{
                    console.warn('Callback reCAPTCHA não disparado:', e);
                }}
            }})();
        """)
        logger.info("Token reCAPTCHA injetado na página.")


class ImageCaptchaSolver:
    """
    Resolve CAPTCHA simples de imagem (texto/números) via 2Captcha.
    Usado em portais ASP.NET como RF1Consig que geram imagem própria.

    Fluxo:
      1. Baixa a imagem do CAPTCHA usando os cookies da sessão atual
      2. Envia como base64 para a API do 2Captcha (method=base64)
      3. Aguarda e retorna o texto resolvido
    """

    def __init__(self) -> None:
        self.api_key = settings.TWOCAPTCHA_API_KEY
        if not self.api_key:
            raise RuntimeError(
                "TWOCAPTCHA_API_KEY não configurada. "
                "Adicione TWOCAPTCHA_API_KEY=sua_chave ao arquivo .env "
                "para usar portais com CAPTCHA de imagem."
            )

    def resolver_elemento(self, page, seletor_img: str) -> str:
        """
        Captura a imagem do CAPTCHA via URL absoluta com cookies da sessão,
        envia ao 2Captcha e retorna o texto resolvido.

        Args:
            page:         Playwright page ativa.
            seletor_img:  Seletor CSS do elemento <img> do CAPTCHA.

        Returns:
            Texto do CAPTCHA (ex: "A3K9").

        Raises:
            RuntimeError: se o elemento não for encontrado ou API falhar.
        """
        import base64
        from urllib.parse import urljoin
        import httpx as _httpx

        # ── 1. Localiza e baixa a imagem ──────────────────────────────────────
        img_loc = page.locator(seletor_img)
        if img_loc.count() == 0:
            raise RuntimeError(
                f"Imagem CAPTCHA não encontrada com seletor '{seletor_img}'."
            )

        img_src = img_loc.first.get_attribute("src") or ""
        if not img_src:
            raise RuntimeError("Atributo src da imagem CAPTCHA está vazio.")

        # Resolve URL relativa
        if not img_src.startswith("http"):
            img_src = urljoin(page.url, img_src)

        # Adiciona timestamp para forçar novo CAPTCHA a cada tentativa
        import time as _time
        img_url = f"{img_src}?ts={int(_time.time())}"

        # Usa cookies da sessão para baixar a imagem
        cookies_list = page.context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies_list)

        logger.info("[ImageCaptcha] Baixando CAPTCHA de: %s", img_src)
        with _httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(img_url, headers={"Cookie": cookie_str})
            resp.raise_for_status()

        img_b64 = base64.b64encode(resp.content).decode()
        logger.info("[ImageCaptcha] Imagem capturada (%d bytes)", len(resp.content))

        # ── 2. Envia ao 2Captcha ──────────────────────────────────────────────
        with _httpx.Client(timeout=30) as client:
            resp = client.post(_URL_SUBMIT, data={
                "key":    self.api_key,
                "method": "base64",
                "body":   img_b64,
                "json":   1,
            })
            resp.raise_for_status()
            dados_submit = resp.json()

        if dados_submit.get("status") != 1:
            raise RuntimeError(
                f"2Captcha recusou a imagem: {dados_submit.get('request', dados_submit)}"
            )

        captcha_id = dados_submit["request"]
        logger.info("[ImageCaptcha] Tarefa criada no 2Captcha | ID: %s", captcha_id)

        # ── 3. Aguarda solução ────────────────────────────────────────────────
        _time.sleep(5)
        deadline = _time.time() + 60

        while _time.time() < deadline:
            with _httpx.Client(timeout=30) as client:
                resp = client.get(_URL_RESULT, params={
                    "key":    self.api_key,
                    "action": "get",
                    "id":     captcha_id,
                    "json":   1,
                })
                resp.raise_for_status()
                dados_result = resp.json()

            request_val = dados_result.get("request", "")

            if dados_result.get("status") == 1:
                logger.info("[ImageCaptcha] Resolvido: '%s'", request_val)
                return request_val

            if request_val == "ERROR_CAPTCHA_UNSOLVABLE":
                raise CaptchaUnsolvableError(
                    "2Captcha não conseguiu ler o CAPTCHA de imagem."
                )

            if request_val.startswith("ERROR_"):
                raise RuntimeError(f"Erro 2Captcha: {request_val}")

            _time.sleep(5)

        raise CaptchaTimeoutError("Timeout: 2Captcha não resolveu a imagem em 60s.")
