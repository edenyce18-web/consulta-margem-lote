"""
crypto.py — Criptografia AES-256-GCM para dados sensíveis (credenciais de bancos).

Uso:
    from app.crypto import encrypt, decrypt

    enc = encrypt("minha_senha_secreta", settings.ENCRYPTION_KEY)
    plain = decrypt(enc, settings.ENCRYPTION_KEY)

Formato do ciphertext: base64url(nonce[12 bytes] + ciphertext + tag[16 bytes])
"""

from __future__ import annotations

import os
import base64
import logging

logger = logging.getLogger(__name__)


def _get_key(key_b64: str) -> bytes:
    try:
        key = base64.b64decode(key_b64 + "==")   # padding tolerante
    except Exception as exc:
        raise ValueError(f"ENCRYPTION_KEY inválida (não é base64): {exc}") from exc
    if len(key) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY deve ter exatamente 32 bytes (256 bits). "
            f"Atual: {len(key)} bytes. "
            f"Gere com: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
        )
    return key


def encrypt(plaintext: str, key_b64: str) -> str:
    """
    Criptografa `plaintext` com AES-256-GCM.

    Returns:
        String base64 contendo nonce (12 bytes) + ciphertext + tag (16 bytes).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key(key_b64)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(encrypted: str, key_b64: str) -> str:
    """
    Descriptografa string produzida por `encrypt`.

    Args:
        encrypted: String base64 (nonce + ciphertext + tag).
        key_b64:   Chave AES-256 em base64.

    Returns:
        Plaintext original.

    Raises:
        cryptography.exceptions.InvalidTag: se ciphertext foi adulterado.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _get_key(key_b64)
    aesgcm = AESGCM(key)
    data = base64.b64decode(encrypted)
    if len(data) < 28:   # 12 nonce + 16 tag mínimos
        raise ValueError("Dados criptografados inválidos: tamanho insuficiente.")
    nonce, ciphertext = data[:12], data[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
