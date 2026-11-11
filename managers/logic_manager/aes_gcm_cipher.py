"""AesGcmCipher: encrypts files with AES-256-GCM."""

import base64
import binascii
import os
import secrets
from typing import Any

from models import EncryptionKeyError, FileCipher, FileDecryptionError

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # handled in AesGcmCipher.__init__
    AESGCM = None
    InvalidTag = None


class AesGcmCipher(FileCipher):
    """Encrypts files with AES-256-GCM. Saved as MAGIC + nonce + ciphertext + tag.
    The tag detects a wrong key or an edited file."""

    KEY_ENV_VAR = "DATA_ENCRYPTION_KEY"
    KEY_BYTES = 32
    NONCE_BYTES = 12
    TAG_BYTES = 16

    def __init__(self, key: bytes) -> None:
        if AESGCM is None:
            raise EncryptionKeyError(
                "missing_library",
                "The 'cryptography' package is not installed "
                "(run: python -m pip install -r requirements.txt).",
            )
        if not isinstance(key, bytes) or len(key) != self.KEY_BYTES:
            raise EncryptionKeyError(
                "wrong_length",
                f"The encryption key must be exactly {self.KEY_BYTES} bytes.",
            )
        # private (encapsulation): the key can't be read from outside
        self.__aes = AESGCM(key)

    @classmethod
    def from_base64(cls, text: Any) -> "AesGcmCipher":
        text = str(text or "").strip()
        if not text:
            raise EncryptionKeyError(
                "missing", f"{cls.KEY_ENV_VAR} is not set."
            )
        try:
            key = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            raise EncryptionKeyError(
                "not_base64", f"{cls.KEY_ENV_VAR} is not valid base64 text."
            ) from None
        if len(key) != cls.KEY_BYTES:
            raise EncryptionKeyError(
                "wrong_length",
                f"{cls.KEY_ENV_VAR} must decode to {cls.KEY_BYTES} bytes "
                f"(it decodes to {len(key)}).",
            )
        return cls(key)

    @classmethod
    def from_environment(cls) -> "AesGcmCipher":
        return cls.from_base64(os.environ.get(cls.KEY_ENV_VAR))

    @classmethod
    def generate_key(cls) -> str:
        return base64.b64encode(secrets.token_bytes(cls.KEY_BYTES)).decode("ascii")

    @property
    def encrypts(self) -> bool:
        return True

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = secrets.token_bytes(self.NONCE_BYTES)  # new nonce every save
        return self.MAGIC + nonce + self.__aes.encrypt(nonce, plaintext, self.MAGIC)

    def decrypt(self, stored: bytes) -> bytes:
        if not self.is_encrypted(stored):
            # Don't trust plain files, otherwise someone could swap in their own users.json
            raise FileDecryptionError(
                "not_encrypted",
                "This file is not encrypted. Run "
                "'python main.py --encrypt-existing-data' once to convert it.",
            )
        body = stored[len(self.MAGIC):]
        if len(body) < self.NONCE_BYTES + self.TAG_BYTES:
            raise FileDecryptionError(
                "damaged", "This encrypted file is incomplete (truncated)."
            )
        nonce, ciphertext = body[: self.NONCE_BYTES], body[self.NONCE_BYTES:]
        try:
            return self.__aes.decrypt(nonce, ciphertext, self.MAGIC)
        except InvalidTag:
            raise FileDecryptionError(
                "wrong_key",
                "This file could not be decrypted: the encryption key is wrong "
                "or the file was modified.",
            ) from None
