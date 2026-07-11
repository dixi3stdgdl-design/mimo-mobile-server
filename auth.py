"""
Authentication module — JWT tokens + API keys for SaaS mode.

Supports:
- Legacy PIN auth (backward compatible)
- JWT token auth (for SaaS)
- API key auth (for programmatic access)
"""

import os
import time
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple


# JWT Implementation (minimal, no external deps)
class JWT:
    """Minimal JWT implementation using HMAC-SHA256."""

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        import base64
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def _b64url_decode(s: str) -> bytes:
        import base64
        s += "=" * (4 - len(s) % 4)
        return base64.urlsafe_b64decode(s)

    @staticmethod
    def encode(payload: dict, secret: str, expires_in: int = 86400) -> str:
        """Create a JWT token."""
        header = {"alg": "HS256", "typ": "JWT"}
        
        now = int(time.time())
        payload["iat"] = now
        payload["exp"] = now + expires_in
        
        header_encoded = JWT._b64url_encode(json.dumps(header).encode())
        payload_encoded = JWT._b64url_encode(json.dumps(payload).encode())
        
        signing_input = f"{header_encoded}.{payload_encoded}"
        signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        signature_encoded = JWT._b64url_encode(signature)
        
        return f"{header_encoded}.{payload_encoded}.{signature_encoded}"

    @staticmethod
    def decode(token: str, secret: str) -> Optional[dict]:
        """Decode and verify a JWT token. Returns None if invalid."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            
            header_encoded, payload_encoded, signature_encoded = parts
            
            # Verify signature
            signing_input = f"{header_encoded}.{payload_encoded}"
            expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
            actual_sig = JWT._b64url_decode(signature_encoded)
            
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            
            # Decode payload
            payload = json.loads(JWT._b64url_decode(payload_encoded))
            
            # Check expiration
            if "exp" in payload and payload["exp"] < time.time():
                return None
            
            return payload
            
        except Exception:
            return None


class AuthManager:
    """Manages authentication for MiMo Server."""

    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or os.environ.get("MIMO_JWT_SECRET", secrets.token_hex(32))
        self.api_keys = {}  # api_key -> {user_id, tier, created_at}
        self.users = {}  # user_id -> {password_hash, tier, created_at}
        
        # Load from env if configured
        self._load_from_env()

    def _load_from_env(self):
        """Load auth configuration from environment."""
        # API keys
        api_keys_str = os.environ.get("MIMO_API_KEYS", "")
        if api_keys_str:
            for key_pair in api_keys_str.split(","):
                if ":" in key_pair:
                    api_key, user_id = key_pair.split(":", 1)
                    self.api_keys[api_key.strip()] = {
                        "user_id": user_id.strip(),
                        "tier": "pro",
                        "created_at": time.time()
                    }

    # ─── PIN Auth (Legacy) ───────────────────────────────────────────

    def verify_pin(self, pin: str, expected_pin: str) -> bool:
        """Verify PIN with constant-time comparison."""
        return hmac.compare_digest(pin.encode(), expected_pin.encode())

    # ─── JWT Auth ─────────────────────────────────────────────────────

    def create_token(self, user_id: str, tier: str = "free", expires_in: int = 86400) -> str:
        """Create a JWT token for a user."""
        return JWT.encode(
            {"sub": user_id, "tier": tier},
            self.secret_key,
            expires_in
        )

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token."""
        return JWT.decode(token, self.secret_key)

    # ─── API Key Auth ─────────────────────────────────────────────────

    def create_api_key(self, user_id: str, tier: str = "pro") -> str:
        """Generate a new API key."""
        api_key = f"mimo_{secrets.token_hex(24)}"
        self.api_keys[api_key] = {
            "user_id": user_id,
            "tier": tier,
            "created_at": time.time()
        }
        return api_key

    def verify_api_key(self, api_key: str) -> Optional[dict]:
        """Verify an API key."""
        return self.api_keys.get(api_key)

    # ─── User Management ──────────────────────────────────────────────

    def create_user(self, user_id: str, password: str, tier: str = "free") -> bool:
        """Create a new user."""
        if user_id in self.users:
            return False
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        self.users[user_id] = {
            "password_hash": password_hash,
            "tier": tier,
            "created_at": time.time()
        }
        return True

    def verify_user(self, user_id: str, password: str) -> Optional[dict]:
        """Verify user credentials."""
        user = self.users.get(user_id)
        if not user:
            return None
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if not hmac.compare_digest(user["password_hash"], password_hash):
            return None
        
        return {"user_id": user_id, "tier": user["tier"]}

    # ─── Unified Auth ─────────────────────────────────────────────────

    def authenticate(self, auth_data: dict, legacy_pin: str) -> Tuple[bool, str, dict]:
        """
        Unified authentication method.
        
        Args:
            auth_data: {"type": "pin"|"token"|"api_key", "value": "..."}
            legacy_pin: The expected PIN for legacy auth
            
        Returns:
            (success, user_id, metadata)
        """
        auth_type = auth_data.get("type", "pin")
        value = auth_data.get("value", "")
        
        if auth_type == "pin":
            if self.verify_pin(value, legacy_pin):
                return True, "local", {"tier": "local"}
            return False, "", {}
        
        elif auth_type == "token":
            payload = self.verify_token(value)
            if payload:
                return True, payload.get("sub", ""), {"tier": payload.get("tier", "free")}
            return False, "", {}
        
        elif auth_type == "api_key":
            key_data = self.verify_api_key(value)
            if key_data:
                return True, key_data["user_id"], {"tier": key_data["tier"]}
            return False, "", {}
        
        return False, "", {}


# Singleton
_auth_manager = None

def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager
