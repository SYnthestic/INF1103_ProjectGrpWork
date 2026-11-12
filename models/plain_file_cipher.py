"""PlainFileCipher: fileCipher that doesn't encrypt."""

from .file_cipher import FileCipher
from .file_decryption_error import FileDecryptionError


class PlainFileCipher(FileCipher):
    """FileCipher that doesn't encrypt. Used in tests."""

    @property
    def encrypts(self) -> bool:
        return False

    def encrypt(self, plaintext: bytes) -> bytes:
        return plaintext

    def decrypt(self, stored: bytes) -> bytes:
        if self.is_encrypted(stored):
            raise FileDecryptionError(
                "no_key", "This file is encrypted, but no encryption key is in use."
            )
        return stored
