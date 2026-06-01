"""ImageVault encryption engine — AES-256-GCM with PBKDF2 + HKDF key derivation."""
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SALT_LENGTH = 16
NONCE_LENGTH = 12
KEY_LENGTH = 32          # AES-256
PBKDF2_ITERATIONS = 600_000
MAGIC = b'IVLT'           # 4-byte verification prefix
APP_SALT = b'ImageVault\x00MasterKeySalt\x01'  # fixed PBKDF2 salt


class CryptoEngine:
    """Derives a master key from password, then per-file keys via HKDF."""

    def __init__(self, password: str):
        self._master_key = self._derive_master_key(password)
        self._aesgcm = AESGCM(self._master_key)

    # ------------------------------------------------------------------
    # key derivation
    # ------------------------------------------------------------------

    def _derive_master_key(self, password: str) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=APP_SALT,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(password.encode('utf-8'))

    def _derive_file_key(self, file_salt: bytes) -> bytes:
        h = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=file_salt,
            info=b'file-key',
            backend=default_backend(),
        )
        return h.derive(self._master_key)

    # ------------------------------------------------------------------
    # encrypt / decrypt
    # ------------------------------------------------------------------

    def encrypt_image(self, image_bytes: bytes) -> bytes:
        """Encrypt raw image bytes. Returns salt + nonce + AES-GCM ciphertext."""
        file_salt = os.urandom(SALT_LENGTH)
        nonce = os.urandom(NONCE_LENGTH)
        file_key = self._derive_file_key(file_salt)
        plaintext = MAGIC + image_bytes
        ciphertext = AESGCM(file_key).encrypt(nonce, plaintext, None)
        return file_salt + nonce + ciphertext

    def decrypt_image(self, encrypted_bytes: bytes) -> bytes:
        """Decrypt encrypted bytes. Returns raw image bytes.

        Raises ValueError on wrong password or corrupt data.
        """
        file_salt = encrypted_bytes[:SALT_LENGTH]
        nonce = encrypted_bytes[SALT_LENGTH:SALT_LENGTH + NONCE_LENGTH]
        ciphertext = encrypted_bytes[SALT_LENGTH + NONCE_LENGTH:]
        file_key = self._derive_file_key(file_salt)
        try:
            plaintext = AESGCM(file_key).decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("Wrong password or corrupted file")
        if not plaintext.startswith(MAGIC):
            raise ValueError("Wrong password or corrupted file")
        return plaintext[len(MAGIC):]

    def zero_master_key(self) -> None:
        """Overwrite master key in memory for secure cleanup."""
        if hasattr(self, '_master_key'):
            self._master_key = b'\x00' * KEY_LENGTH
