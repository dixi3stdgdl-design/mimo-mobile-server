"""Tests for authentication module."""

import pytest
import time
from auth import JWT, AuthManager


class TestJWT:
    """Tests for JWT implementation."""

    def test_encode_decode(self):
        token = JWT.encode({"user_id": "test"}, "secret123", 3600)
        payload = JWT.decode(token, "secret123")
        assert payload is not None
        assert payload["user_id"] == "test"
        assert "exp" in payload
        assert "iat" in payload

    def test_invalid_signature(self):
        token = JWT.encode({"user_id": "test"}, "secret123", 3600)
        payload = JWT.decode(token, "wrong_secret")
        assert payload is None

    def test_expired_token(self):
        token = JWT.encode({"user_id": "test"}, "secret123", -1)  # Already expired
        payload = JWT.decode(token, "secret123")
        assert payload is None

    def test_malformed_token(self):
        payload = JWT.decode("not.a.valid.token", "secret")
        assert payload is None

    def test_empty_token(self):
        payload = JWT.decode("", "secret")
        assert payload is None


class TestAuthManager:
    """Tests for AuthManager."""

    def setup_method(self):
        self.auth = AuthManager("test_secret_key")

    def test_pin_verification(self):
        assert self.auth.verify_pin("MIMO2026", "MIMO2026") is True
        assert self.auth.verify_pin("wrong", "MIMO2026") is False

    def test_create_verify_token(self):
        token = self.auth.create_token("user1", "pro", 3600)
        payload = self.auth.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user1"
        assert payload["tier"] == "pro"

    def test_create_api_key(self):
        api_key = self.auth.create_api_key("user1", "pro")
        assert api_key.startswith("mimo_")
        
        result = self.auth.verify_api_key(api_key)
        assert result is not None
        assert result["user_id"] == "user1"
        assert result["tier"] == "pro"

    def test_invalid_api_key(self):
        result = self.auth.verify_api_key("invalid_key")
        assert result is None

    def test_create_user(self):
        result = self.auth.create_user("user1", "password123", "free")
        assert result is True
        
        # Duplicate user
        result = self.auth.create_user("user1", "password123", "free")
        assert result is False

    def test_verify_user(self):
        self.auth.create_user("user1", "password123", "pro")
        
        result = self.auth.verify_user("user1", "password123")
        assert result is not None
        assert result["user_id"] == "user1"
        assert result["tier"] == "pro"
        
        # Wrong password
        result = self.auth.verify_user("user1", "wrong_password")
        assert result is None
        
        # Non-existent user
        result = self.auth.verify_user("nonexistent", "password")
        assert result is None

    def test_authenticate_pin(self):
        success, user_id, meta = self.auth.authenticate(
            {"type": "pin", "value": "MIMO2026"},
            "MIMO2026"
        )
        assert success is True
        assert user_id == "local"
        assert meta["tier"] == "local"

    def test_authenticate_pin_wrong(self):
        success, user_id, meta = self.auth.authenticate(
            {"type": "pin", "value": "wrong"},
            "MIMO2026"
        )
        assert success is False

    def test_authenticate_token(self):
        token = self.auth.create_token("user1", "pro")
        success, user_id, meta = self.auth.authenticate(
            {"type": "token", "value": token},
            "MIMO2026"
        )
        assert success is True
        assert user_id == "user1"
        assert meta["tier"] == "pro"

    def test_authenticate_api_key(self):
        api_key = self.auth.create_api_key("user1", "pro")
        success, user_id, meta = self.auth.authenticate(
            {"type": "api_key", "value": api_key},
            "MIMO2026"
        )
        assert success is True
        assert user_id == "user1"
        assert meta["tier"] == "pro"

    def test_authenticate_unknown_type(self):
        success, user_id, meta = self.auth.authenticate(
            {"type": "unknown", "value": "test"},
            "MIMO2026"
        )
        assert success is False
