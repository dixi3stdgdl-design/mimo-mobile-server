"""Tests for production hardening: rate limiter, logging, CORS, metrics, env validation."""

import logging
import unittest
import json
import time
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from rate_limiter import RateLimiter, get_rate_limiter
from logging_config import JSONFormatter, log_request
from cors_config import get_cors_origins, apply_cors_headers
from metrics import HTTP_REQUEST_DURATION


class TestRateLimiter(unittest.TestCase):
    """Test in-memory sliding window rate limiter."""

    def test_allows_requests_under_limit(self):
        limiter = RateLimiter(rate_limit=5, window_seconds=60)
        for _ in range(5):
            self.assertTrue(limiter.is_allowed("1.2.3.4"))

    def test_blocks_requests_over_limit(self):
        limiter = RateLimiter(rate_limit=3, window_seconds=60)
        self.assertTrue(limiter.is_allowed("1.2.3.4"))
        self.assertTrue(limiter.is_allowed("1.2.3.4"))
        self.assertTrue(limiter.is_allowed("1.2.3.4"))
        self.assertFalse(limiter.is_allowed("1.2.3.4"))

    def test_separate_ips(self):
        limiter = RateLimiter(rate_limit=2, window_seconds=60)
        self.assertTrue(limiter.is_allowed("1.1.1.1"))
        self.assertTrue(limiter.is_allowed("1.1.1.1"))
        self.assertFalse(limiter.is_allowed("1.1.1.1"))
        # Different IP still allowed
        self.assertTrue(limiter.is_allowed("2.2.2.2"))

    def test_reset_single_ip(self):
        limiter = RateLimiter(rate_limit=1, window_seconds=60)
        limiter.is_allowed("1.1.1.1")
        self.assertFalse(limiter.is_allowed("1.1.1.1"))
        limiter.reset("1.1.1.1")
        self.assertTrue(limiter.is_allowed("1.1.1.1"))

    def test_reset_all(self):
        limiter = RateLimiter(rate_limit=1, window_seconds=60)
        limiter.is_allowed("1.1.1.1")
        limiter.is_allowed("2.2.2.2")
        limiter.reset()
        self.assertTrue(limiter.is_allowed("1.1.1.1"))
        self.assertTrue(limiter.is_allowed("2.2.2.2"))

    def test_window_expiration(self):
        limiter = RateLimiter(rate_limit=2, window_seconds=0)
        limiter.is_allowed("1.1.1.1")
        limiter.is_allowed("1.1.1.1")
        # Window is 0 seconds, so entries expire immediately
        self.assertTrue(limiter.is_allowed("1.1.1.1"))

    def test_singleton(self):
        l1 = get_rate_limiter()
        l2 = get_rate_limiter()
        self.assertIs(l1, l2)


class TestJSONFormatter(unittest.TestCase):
    """Test structured JSON log formatter."""

    def test_format_basic(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None
        )
        output = formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["message"], "test message")
        self.assertIn("timestamp", data)

    def test_format_with_extra(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="GET /api 200 5ms", args=(), exc_info=None
        )
        record.method = "GET"
        record.path = "/api"
        record.status = 200
        record.duration_ms = 5.0
        record.ip = "127.0.0.1"
        output = formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data["method"], "GET")
        self.assertEqual(data["path"], "/api")
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["duration_ms"], 5.0)
        self.assertEqual(data["ip"], "127.0.0.1")


class TestCORSConfig(unittest.TestCase):
    """Test CORS configuration."""

    def test_default_origins(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIMO_CORS_ORIGINS", None)
            origins = get_cors_origins()
            self.assertEqual(origins, ["*"])

    def test_custom_origins(self):
        with patch.dict(os.environ, {"MIMO_CORS_ORIGINS": "https://app.com,https://admin.com"}):
            origins = get_cors_origins()
            self.assertEqual(origins, ["https://app.com", "https://admin.com"])

    def test_apply_cors_headers_wildcard(self):
        with patch("cors_config.CORS_ORIGINS", ["*"]):
            handler = MagicMock()
            apply_cors_headers(handler, "https://any.com")
            handler.send_header.assert_any_call("Access-Control-Allow-Origin", "*")

    def test_apply_cors_headers_specific(self):
        with patch("cors_config.CORS_ORIGINS", ["https://app.com"]):
            handler = MagicMock()
            apply_cors_headers(handler, "https://app.com")
            handler.send_header.assert_any_call("Access-Control-Allow-Origin", "https://app.com")


class TestHTTPRequestDuration(unittest.TestCase):
    """Test HTTP request duration histogram metric exists."""

    def test_histogram_exists(self):
        self.assertIsNotNone(HTTP_REQUEST_DURATION)

    def test_histogram_observe(self):
        HTTP_REQUEST_DURATION.labels(method="GET", path="/test").observe(0.1)


class TestEnvValidation(unittest.TestCase):
    """Test environment variable validation."""

    def test_validate_env_missing_jwt_secret(self):
        from config import validate_env
        with patch.dict(os.environ, {"MIMO_JWT_SECRET": ""}, clear=False):
            with self.assertRaises(SystemExit):
                validate_env()

    def test_validate_env_valid(self):
        from config import validate_env
        with patch.dict(os.environ, {
            "MIMO_JWT_SECRET": "test-secret-key",
            "MIMO_WS_PORT": "8765",
            "MIMO_HTTP_PORT": "8080"
        }, clear=False):
            # Should not raise
            validate_env()

    def test_validate_env_bad_port(self):
        from config import validate_env
        with patch.dict(os.environ, {
            "MIMO_JWT_SECRET": "test-secret-key",
            "MIMO_WS_PORT": "99999",
            "MIMO_HTTP_PORT": "8080"
        }, clear=False):
            with self.assertRaises(SystemExit):
                validate_env()

    def test_validate_env_same_port(self):
        from config import validate_env
        with patch.dict(os.environ, {
            "MIMO_JWT_SECRET": "test-secret-key",
            "MIMO_WS_PORT": "8080",
            "MIMO_HTTP_PORT": "8080"
        }, clear=False):
            with self.assertRaises(SystemExit):
                validate_env()


if __name__ == '__main__':
    unittest.main()
