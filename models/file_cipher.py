"""FileCipher: interface for encrypting data files."""

from abc import ABC, abstractmethod


class FileCipher(ABC):
    """Interface for encrypting data files. DataManager uses any FileCipher
    without knowing which one (polymorphism)."""

    # Header on every encrypted file, so we can tell it apart from plain JSON.
    MAGIC = b"SMEENC1"

    @property
    @abstractmethod
    def encrypts(self) -> bool: ...

    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        """Returns the bytes to save to disk."""

    @abstractmethod
    def decrypt(self, stored: bytes) -> bytes:
        """Returns the original JSON bytes. Raises FileDecryptionError."""

    @classmethod
    def is_encrypted(cls, stored: bytes) -> bool:
        return stored.startswith(cls.MAGIC)
