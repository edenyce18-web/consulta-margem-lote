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
