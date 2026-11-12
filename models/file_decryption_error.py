"""FileDecryptionError: file can't be decrypted."""



class FileDecryptionError(Exception):
    """File can't be decrypted. reason: no_key, not_encrypted, damaged or wrong_key.
    The file is never changed, since the key might just be wrong."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
