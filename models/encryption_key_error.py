"""EncryptionKeyError: key is missing or invalid."""



class EncryptionKeyError(ValueError):
    """Key is missing or invalid. reason: missing / not_base64 / wrong_length."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
