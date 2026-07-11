"""Tests for B2B module."""

import pytest
import tempfile
import os
from b2b import B2BManager, B2BDatabase, Role, Organization


@pytest.fixture
def b2b():
    """Create fresh B2B manager for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    db = B2BDatabase(db_path)
    manager = B2BManager()
    manager.db = db
    
    yield manager
    
    os.unlink(db_path)


class TestOrganization:
    def test_create_organization(self, b2b):
        org = b2b.create_organization("Acme Corp", "user1", "business")
        assert org.name == "Acme Corp"
        assert org.plan == "business"
        assert org.id.startswith("org_")

    def test_get_organization(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        fetched = b2b.get_organization(org.id)
        assert fetched is not None
        assert fetched.name == "Test Org"

    def test_get_organization_by_slug(self, b2b):
        org = b2b.create_organization("My Company", "user1")
        fetched = b2b.get_organization_by_slug("my-company")
        assert fetched is not None
        assert fetched.id == org.id

    def test_update_organization(self, b2b):
        org = b2b.create_organization("Old Name", "user1")
        b2b.update_organization(org.id, name="New Name")
        fetched = b2b.get_organization(org.id)
        assert fetched.name == "New Name"

    def test_delete_organization(self, b2b):
        org = b2b.create_organization("To Delete", "user1")
        assert b2b.delete_organization(org.id) is True
        assert b2b.get_organization(org.id) is None


class TestMembers:
    def test_add_member(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        member = b2b.add_member(org.id, "user2", Role.MANAGER)
        assert member.role == Role.MANAGER

    def test_get_member(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.USER)
        member = b2b.get_member(org.id, "user2")
        assert member is not None
        assert member.role == Role.USER

    def test_get_organization_members(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.MANAGER)
        b2b.add_member(org.id, "user3", Role.USER)
        
        members = b2b.get_organization_members(org.id)
        assert len(members) == 3  # Including owner

    def test_remove_member(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.USER)
        assert b2b.remove_member(org.id, "user2") is True
        assert b2b.get_member(org.id, "user2") is None

    def test_update_member_role(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.USER)
        b2b.update_member_role(org.id, "user2", Role.ADMIN)
        member = b2b.get_member(org.id, "user2")
        assert member.role == Role.ADMIN


class TestInvitations:
    def test_create_invitation(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        inv = b2b.create_invitation(org.id, "new@example.com", Role.MANAGER, "user1")
        assert inv.email == "new@example.com"
        assert inv.role == Role.MANAGER

    def test_accept_invitation(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        inv = b2b.create_invitation(org.id, "new@example.com", Role.USER, "user1")
        
        member = b2b.accept_invitation(inv.token, "user_new")
        assert member is not None
        assert member.role == Role.USER

    def test_invalid_invitation_token(self, b2b):
        result = b2b.accept_invitation("invalid_token", "user_new")
        assert result is None


class TestRBAC:
    def test_owner_can_manage(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        assert b2b.check_permission(org.id, "user1", "org.manage") is True
        assert b2b.check_permission(org.id, "user1", "members.manage") is True

    def test_admin_permissions(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.ADMIN)
        
        assert b2b.check_permission(org.id, "user2", "members.manage") is True
        assert b2b.check_permission(org.id, "user2", "org.manage") is True
        assert b2b.check_permission(org.id, "user2", "billing.manage") is False

    def test_user_permissions(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.USER)
        
        assert b2b.check_permission(org.id, "user2", "chat.use") is True
        assert b2b.check_permission(org.id, "user2", "members.manage") is False

    def test_viewer_permissions(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.add_member(org.id, "user2", Role.VIEWER)
        
        assert b2b.check_permission(org.id, "user2", "projects.view") is True
        assert b2b.check_permission(org.id, "user2", "chat.use") is False


class TestAuditLog:
    def test_log_event(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.log_event(org.id, "user1", "project.created", "project", "proj_123")
        
        events = b2b.get_audit_log(org.id)
        assert len(events) == 1
        assert events[0].action == "project.created"

    def test_audit_log_with_filter(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        b2b.log_event(org.id, "user1", "project.created")
        b2b.log_event(org.id, "user1", "member.invited")
        
        events = b2b.get_audit_log(org.id, action="project.created")
        assert len(events) == 1


class TestAPIKeys:
    def test_create_api_key(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        key_id, raw_key = b2b.create_api_key(org.id, "Test Key", "user1")
        
        assert key_id.startswith("ak_")
        assert raw_key.startswith("mimo_")

    def test_verify_api_key(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        key_id, raw_key = b2b.create_api_key(org.id, "Test Key", "user1")
        
        result = b2b.verify_api_key(raw_key)
        assert result is not None
        assert result["org_id"] == org.id

    def test_revoke_api_key(self, b2b):
        org = b2b.create_organization("Test Org", "user1")
        key_id, raw_key = b2b.create_api_key(org.id, "Test Key", "user1")
        
        b2b.revoke_api_key(key_id)
        result = b2b.verify_api_key(raw_key)
        assert result is None
