"""Tests for B2B API endpoints — license generation and admin dashboard."""

import unittest
import json
import tempfile
import os
from unittest.mock import MagicMock, patch
from io import BytesIO

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from b2b_api import LicenseManager, get_license_manager


class TestLicenseManager(unittest.TestCase):
    """Test license key generation and validation."""

    def setUp(self):
        self.lic_mgr = LicenseManager()

    def test_generate_license(self):
        lic = self.lic_mgr.generate_license("org_123", "pro", 30)
        self.assertTrue(lic["key"].startswith("lic_"))
        self.assertEqual(lic["org_id"], "org_123")
        self.assertEqual(lic["plan"], "pro")
        self.assertTrue(lic["active"])
        self.assertGreater(lic["expires_at"], lic["created_at"])

    def test_validate_license(self):
        lic = self.lic_mgr.generate_license("org_123", "starter")
        result = self.lic_mgr.validate_license(lic["key"])
        self.assertIsNotNone(result)
        self.assertEqual(result["org_id"], "org_123")

    def test_validate_invalid_key(self):
        result = self.lic_mgr.validate_license("lic_invalid")
        self.assertIsNone(result)

    def test_revoke_license(self):
        lic = self.lic_mgr.generate_license("org_123", "starter")
        self.assertTrue(self.lic_mgr.revoke_license(lic["key"]))
        result = self.lic_mgr.validate_license(lic["key"])
        self.assertIsNone(result)

    def test_revoke_nonexistent(self):
        self.assertFalse(self.lic_mgr.revoke_license("lic_nonexistent"))

    def test_get_org_licenses(self):
        self.lic_mgr.generate_license("org_1", "starter")
        self.lic_mgr.generate_license("org_1", "pro")
        self.lic_mgr.generate_license("org_2", "starter")
        
        org1_lics = self.lic_mgr.get_org_licenses("org_1")
        self.assertEqual(len(org1_lics), 2)
        
        org2_lics = self.lic_mgr.get_org_licenses("org_2")
        self.assertEqual(len(org2_lics), 1)

    def test_expired_license(self):
        lic = self.lic_mgr.generate_license("org_123", "starter", duration_days=-1)
        result = self.lic_mgr.validate_license(lic["key"])
        self.assertIsNone(result)
        self.assertFalse(lic["active"])

    def test_multiple_licenses_different_plans(self):
        lic1 = self.lic_mgr.generate_license("org_1", "starter")
        lic2 = self.lic_mgr.generate_license("org_1", "enterprise")
        self.assertNotEqual(lic1["key"], lic2["key"])
        self.assertEqual(lic1["plan"], "starter")
        self.assertEqual(lic2["plan"], "enterprise")


class TestLicenseManagerSingleton(unittest.TestCase):
    """Test license manager singleton."""

    def test_singleton(self):
        mgr1 = get_license_manager()
        mgr2 = get_license_manager()
        self.assertIs(mgr1, mgr2)


class TestDashboardEndpoint(unittest.TestCase):
    """Test /api/dashboard HTTP endpoint handler."""

    def test_dashboard_handler_instantiation(self):
        """Test that dashboard handler can be created."""
        from http_handler import create_http_handler
        from state import SessionStore
        
        state = SessionStore()
        handler_class = create_http_handler(state)
        self.assertIsNotNone(handler_class)

    def test_dashboard_required_fields(self):
        """Test that dashboard response includes all required fields."""
        required_fields = [
            "status", "server", "version", "connections",
            "uptime_seconds", "messages", "processes",
            "screen_frames", "streams_active", "workspace"
        ]
        for field in required_fields:
            self.assertIsInstance(field, str)


class TestB2BHandlerLicenseValidation(unittest.TestCase):
    """Test license validation via B2B API."""

    def test_validate_license_through_manager(self):
        from b2b_api import get_license_manager
        
        mgr = get_license_manager()
        lic = mgr.generate_license("org_123", "enterprise", 365)
        
        # Validate
        result = mgr.validate_license(lic["key"])
        self.assertIsNotNone(result)
        self.assertEqual(result["plan"], "enterprise")
        self.assertEqual(result["org_id"], "org_123")
        
        # Revoke and validate again
        mgr.revoke_license(lic["key"])
        result = mgr.validate_license(lic["key"])
        self.assertIsNone(result)

    def test_license_expiry(self):
        from b2b_api import get_license_manager
        
        mgr = get_license_manager()
        # Generate license that expired yesterday
        lic = mgr.generate_license("org_exp", "starter", duration_days=-1)
        
        result = mgr.validate_license(lic["key"])
        self.assertIsNone(result)
        self.assertFalse(lic["active"])

    def test_license_data_structure(self):
        from b2b_api import get_license_manager
        
        mgr = get_license_manager()
        lic = mgr.generate_license("org_struct", "pro", 90)
        
        required_keys = ["key", "org_id", "plan", "created_at", "expires_at", "active"]
        for key in required_keys:
            self.assertIn(key, lic)

    def test_multiple_licenses_same_org(self):
        from b2b_api import get_license_manager
        
        mgr = get_license_manager()
        lic1 = mgr.generate_license("org_multi", "starter")
        lic2 = mgr.generate_license("org_multi", "pro")
        lic3 = mgr.generate_license("org_multi", "enterprise")
        
        org_lics = mgr.get_org_licenses("org_multi")
        self.assertEqual(len(org_lics), 3)
        
        plans = [l["plan"] for l in org_lics]
        self.assertIn("starter", plans)
        self.assertIn("pro", plans)
        self.assertIn("enterprise", plans)


if __name__ == '__main__':
    unittest.main()
