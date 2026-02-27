from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass
class SessionState:
    root_key: bytes
    send_chain_key: bytes
    recv_chain_key: bytes
    send_counter: int = 0
    recv_counter: int = 0


class RatchetService:
    """Упрощенный double-ratchet-подобный сервис для E2EE MVP."""

    @staticmethod
    def generate_x25519_keypair() -> tuple[bytes, bytes]:
        priv = x25519.X25519PrivateKey.generate()
        pub = priv.public_key()
        return (
            priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw),
        )

    @staticmethod
    def kyber_keypair_placeholder() -> tuple[bytes, bytes]:
        # Placeholder: интеграция через pqcrypto/liboqs на следующем этапе.
        return os.urandom(32), os.urandom(64)

    @staticmethod
    def init_session(local_private: bytes, remote_public: bytes) -> SessionState:
        shared = x25519.X25519PrivateKey.from_private_bytes(local_private).exchange(
            x25519.X25519PublicKey.from_public_bytes(remote_public)
        )
        hkdf = HKDF(algorithm=hashes.SHA256(), length=96, salt=None, info=b"ddlk-banda-session")
        material = hkdf.derive(shared)
        return SessionState(root_key=material[:32], send_chain_key=material[32:64], recv_chain_key=material[64:96])

    @staticmethod
    def _derive_message_key(chain_key: bytes) -> tuple[bytes, bytes]:
        hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=b"ddlk-banda-msg")
        out = hkdf.derive(chain_key)
        return out[:32], out[32:64]

    @classmethod
    def encrypt_message(cls, session: SessionState, plaintext: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
        next_chain_key, message_key = cls._derive_message_key(session.send_chain_key)
        session.send_chain_key = next_chain_key
        session.send_counter += 1
        nonce = os.urandom(12)
        ciphertext = AESGCM(message_key).encrypt(nonce, plaintext, aad)
        return nonce, ciphertext

    @classmethod
    def decrypt_message(cls, session: SessionState, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
        next_chain_key, message_key = cls._derive_message_key(session.recv_chain_key)
        session.recv_chain_key = next_chain_key
        session.recv_counter += 1
        return AESGCM(message_key).decrypt(nonce, ciphertext, aad)

    @staticmethod
    def reset_session() -> SessionState:
        return SessionState(root_key=os.urandom(32), send_chain_key=os.urandom(32), recv_chain_key=os.urandom(32))
