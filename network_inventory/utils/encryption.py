"""Fernet-based password decryption for device credentials."""
from __future__ import annotations

import stat
import warnings
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken  # noqa: F401  (re-exported for callers)


def load_key(key_file_path: str) -> bytes:
    """Load and return the Fernet key from disk.

    Raises:
        FileNotFoundError: if the key file does not exist.
        PermissionError: if the key file is not readable.
        ValueError: if the key file content is not a valid Fernet key.
    """
    path = Path(key_file_path)
    if not path.exists():
        raise FileNotFoundError(f"Encryption key file not found: {key_file_path}")

    # Warn if world-readable (potential security misconfiguration)
    file_stat = path.stat()
    if file_stat.st_mode & stat.S_IROTH:
        warnings.warn(
            f"Key file {key_file_path} is world-readable. "
            f"Restrict with: chmod 600 {key_file_path}",
            UserWarning,
            stacklevel=2,
        )

    key = path.read_bytes().strip()
    # Validate key is a well-formed Fernet key
    try:
        Fernet(key)
    except Exception as exc:
        raise ValueError(f"Invalid Fernet key in {key_file_path}: {exc}") from exc
    return key


def decrypt_password(key: bytes, encrypted_bytes: bytes) -> str:
    """Decrypt a Fernet-encrypted password and return plaintext string.

    SECURITY: The return value must NEVER be passed to any logging call.
    Call this only inside BaseCollector._connect(); delete the result immediately
    after use.

    Args:
        key: Raw Fernet key bytes (from load_key()).
        encrypted_bytes: Encrypted password bytes from the database.

    Returns:
        Decrypted plaintext password string.

    Raises:
        InvalidToken: if decryption fails (wrong key or corrupted ciphertext).
    """
    f = Fernet(key)
    return f.decrypt(encrypted_bytes).decode("utf-8")
