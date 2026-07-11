"""
B2B Module — Multi-tenancy, RBAC, Audit Logging.

Provides:
- Organization management
- Role-based access control (Admin/Manager/User)
- Audit trail for compliance
- Team invitations
"""

import os
import time
import json
import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from enum import Enum


# ─── Roles ────────────────────────────────────────────────────────────

class Role(Enum):
    OWNER = "owner"      # Full access, billing, delete org
    ADMIN = "admin"      # Manage members, settings
    MANAGER = "manager"  # Manage projects, view analytics
    USER = "user"        # Use features, limited admin
    VIEWER = "viewer"    # Read-only access

    @property
    def level(self) -> int:
        return {
            Role.OWNER: 100,
            Role.ADMIN: 80,
            Role.MANAGER: 60,
            Role.USER: 40,
            Role.VIEWER: 20,
        }[self]

    def can(self, action: str) -> bool:
        """Check if role can perform action."""
        permissions = {
            Role.OWNER: ["*"],
            Role.ADMIN: [
                "org.manage", "members.manage", "members.invite",
                "settings.manage", "projects.manage", "analytics.view",
                "audit.view", "api_keys.manage"
            ],
            Role.MANAGER: [
                "projects.manage", "analytics.view", "members.view"
            ],
            Role.USER: [
                "chat.use", "files.manage", "terminal.use",
                "remote.use", "projects.view"
            ],
            Role.VIEWER: [
                "projects.view", "analytics.view"
            ],
        }
        role_perms = permissions.get(self, [])
        return "*" in role_perms or action in role_perms


# ─── Organization ─────────────────────────────────────────────────────

class Organization:
    """Represents a B2B organization/tenant."""

    def __init__(self, id: str, name: str, slug: str, plan: str = "starter",
                 created_at: float = None, settings: dict = None):
        self.id = id
        self.name = name
        self.slug = slug
        self.plan = plan
        self.created_at = created_at or time.time()
        self.settings = settings or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "plan": self.plan,
            "created_at": self.created_at,
            "settings": self.settings,
        }


# ─── Member ───────────────────────────────────────────────────────────

class Member:
    """Organization member with role."""

    def __init__(self, org_id: str, user_id: str, role: Role,
                 invited_by: str = None, joined_at: float = None):
        self.org_id = org_id
        self.user_id = user_id
        self.role = role
        self.invited_by = invited_by
        self.joined_at = joined_at or time.time()

    def can(self, action: str) -> bool:
        return self.role.can(action)


# ─── Invitation ───────────────────────────────────────────────────────

class Invitation:
    """Pending team invitation."""

    def __init__(self, id: str, org_id: str, email: str, role: Role,
                 invited_by: str, token: str = None, created_at: float = None,
                 expires_at: float = None, accepted: bool = False):
        self.id = id
        self.org_id = org_id
        self.email = email
        self.role = role
        self.invited_by = invited_by
        self.token = token or secrets.token_urlsafe(32)
        self.created_at = created_at or time.time()
        self.expires_at = expires_at or (self.created_at + 7 * 86400)  # 7 days
        self.accepted = accepted

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


# ─── Audit Log ────────────────────────────────────────────────────────

class AuditEvent:
    """Audit log entry for compliance."""

    def __init__(self, org_id: str, user_id: str, action: str,
                 resource_type: str = None, resource_id: str = None,
                 details: dict = None, ip_address: str = None,
                 timestamp: float = None):
        self.org_id = org_id
        self.user_id = user_id
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.details = details or {}
        self.ip_address = ip_address
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat(),
        }


# ─── B2B Database ─────────────────────────────────────────────────────

class B2BDatabase:
    """SQLite database for B2B features."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.environ.get(
            "MIMO_B2B_DB",
            "/data/b2b.db" if os.path.exists("/data") else os.path.expanduser("~/.mimo/b2b.db")
        )
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                plan TEXT DEFAULT 'starter',
                created_at REAL NOT NULL,
                settings TEXT DEFAULT '{}',
                suspended INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS members (
                org_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                invited_by TEXT,
                joined_at REAL NOT NULL,
                PRIMARY KEY (org_id, user_id),
                FOREIGN KEY (org_id) REFERENCES organizations(id)
            );

            CREATE TABLE IF NOT EXISTS invitations (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                invited_by TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                accepted INTEGER DEFAULT 0,
                FOREIGN KEY (org_id) REFERENCES organizations(id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                user_id TEXT,
                key_hash TEXT UNIQUE NOT NULL,
                name TEXT,
                scopes TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                last_used_at REAL,
                expires_at REAL,
                revoked INTEGER DEFAULT 0,
                FOREIGN KEY (org_id) REFERENCES organizations(id)
            );

            CREATE INDEX IF NOT EXISTS idx_members_org ON members(org_id);
            CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);
            CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_log(org_id);
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_api_keys_org ON api_keys(org_id);
        """)
        conn.commit()


# ─── B2B Manager ──────────────────────────────────────────────────────

class B2BManager:
    """Main B2B operations manager."""

    def __init__(self):
        self.db = B2BDatabase()

    # ─── Organization ─────────────────────────────────────────────

    def create_organization(self, name: str, owner_user_id: str,
                           plan: str = "starter") -> Organization:
        """Create a new organization with owner."""
        org_id = f"org_{secrets.token_hex(16)}"
        slug = self._generate_slug(name)
        
        conn = self.db._get_conn()
        conn.execute(
            "INSERT INTO organizations (id, name, slug, plan, created_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, name, slug, plan, time.time())
        )
        
        # Add owner
        conn.execute(
            "INSERT INTO members (org_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (org_id, owner_user_id, Role.OWNER.value, time.time())
        )
        conn.commit()
        
        return Organization(id=org_id, name=name, slug=slug, plan=plan)

    def get_organization(self, org_id: str) -> Optional[Organization]:
        conn = self.db._get_conn()
        row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        if not row:
            return None
        return Organization(
            id=row["id"], name=row["name"], slug=row["slug"],
            plan=row["plan"], created_at=row["created_at"],
            settings=json.loads(row["settings"])
        )

    def get_organization_by_slug(self, slug: str) -> Optional[Organization]:
        conn = self.db._get_conn()
        row = conn.execute("SELECT * FROM organizations WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        return Organization(
            id=row["id"], name=row["name"], slug=row["slug"],
            plan=row["plan"], created_at=row["created_at"],
            settings=json.loads(row["settings"])
        )

    def update_organization(self, org_id: str, **kwargs) -> bool:
        conn = self.db._get_conn()
        allowed = ["name", "plan", "settings"]
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [org_id]
        
        if "settings" in updates:
            updates["settings"] = json.dumps(updates["settings"])
        
        conn.execute(f"UPDATE organizations SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return True

    def delete_organization(self, org_id: str) -> bool:
        conn = self.db._get_conn()
        conn.execute("DELETE FROM audit_log WHERE org_id = ?", (org_id,))
        conn.execute("DELETE FROM api_keys WHERE org_id = ?", (org_id,))
        conn.execute("DELETE FROM invitations WHERE org_id = ?", (org_id,))
        conn.execute("DELETE FROM members WHERE org_id = ?", (org_id,))
        conn.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
        conn.commit()
        return True

    # ─── Members ──────────────────────────────────────────────────

    def add_member(self, org_id: str, user_id: str, role: Role,
                   invited_by: str = None) -> Member:
        conn = self.db._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO members (org_id, user_id, role, invited_by, joined_at) VALUES (?, ?, ?, ?, ?)",
            (org_id, user_id, role.value, invited_by, time.time())
        )
        conn.commit()
        return Member(org_id=org_id, user_id=user_id, role=role, invited_by=invited_by)

    def get_member(self, org_id: str, user_id: str) -> Optional[Member]:
        conn = self.db._get_conn()
        row = conn.execute(
            "SELECT * FROM members WHERE org_id = ? AND user_id = ?",
            (org_id, user_id)
        ).fetchone()
        if not row:
            return None
        return Member(
            org_id=row["org_id"], user_id=row["user_id"],
            role=Role(row["role"]), invited_by=row["invited_by"],
            joined_at=row["joined_at"]
        )

    def get_organization_members(self, org_id: str) -> List[Member]:
        conn = self.db._get_conn()
        rows = conn.execute(
            "SELECT * FROM members WHERE org_id = ? ORDER BY joined_at",
            (org_id,)
        ).fetchall()
        return [
            Member(
                org_id=r["org_id"], user_id=r["user_id"],
                role=Role(r["role"]), invited_by=r["invited_by"],
                joined_at=r["joined_at"]
            ) for r in rows
        ]

    def remove_member(self, org_id: str, user_id: str) -> bool:
        conn = self.db._get_conn()
        conn.execute("DELETE FROM members WHERE org_id = ? AND user_id = ?", (org_id, user_id))
        conn.commit()
        return True

    def update_member_role(self, org_id: str, user_id: str, new_role: Role) -> bool:
        conn = self.db._get_conn()
        conn.execute(
            "UPDATE members SET role = ? WHERE org_id = ? AND user_id = ?",
            (new_role.value, org_id, user_id)
        )
        conn.commit()
        return True

    def get_user_organizations(self, user_id: str) -> List[Dict]:
        """Get all organizations a user belongs to."""
        conn = self.db._get_conn()
        rows = conn.execute("""
            SELECT o.*, m.role FROM organizations o
            JOIN members m ON o.id = m.org_id
            WHERE m.user_id = ?
            ORDER BY o.name
        """, (user_id,)).fetchall()
        return [
            {
                "organization": Organization(
                    id=r["id"], name=r["name"], slug=r["slug"],
                    plan=r["plan"], created_at=r["created_at"]
                ).to_dict(),
                "role": r["role"]
            } for r in rows
        ]

    # ─── Invitations ──────────────────────────────────────────────

    def create_invitation(self, org_id: str, email: str, role: Role,
                         invited_by: str) -> Invitation:
        invitation_id = f"inv_{secrets.token_hex(16)}"
        token = secrets.token_urlsafe(32)
        
        conn = self.db._get_conn()
        conn.execute(
            """INSERT INTO invitations (id, org_id, email, role, invited_by, token, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (invitation_id, org_id, email, role.value, invited_by, token,
             time.time(), time.time() + 7 * 86400)
        )
        conn.commit()
        
        return Invitation(
            id=invitation_id, org_id=org_id, email=email, role=role,
            invited_by=invited_by, token=token
        )

    def get_invitation_by_token(self, token: str) -> Optional[Invitation]:
        conn = self.db._get_conn()
        row = conn.execute(
            "SELECT * FROM invitations WHERE token = ? AND accepted = 0",
            (token,)
        ).fetchone()
        if not row:
            return None
        
        inv = Invitation(
            id=row["id"], org_id=row["org_id"], email=row["email"],
            role=Role(row["role"]), invited_by=row["invited_by"],
            token=row["token"], created_at=row["created_at"],
            expires_at=row["expires_at"], accepted=bool(row["accepted"])
        )
        
        if inv.is_expired:
            return None
        
        return inv

    def accept_invitation(self, token: str, user_id: str) -> Optional[Member]:
        inv = self.get_invitation_by_token(token)
        if not inv:
            return None
        
        conn = self.db._get_conn()
        conn.execute("UPDATE invitations SET accepted = 1 WHERE token = ?", (token,))
        conn.execute(
            "INSERT OR REPLACE INTO members (org_id, user_id, role, invited_by, joined_at) VALUES (?, ?, ?, ?, ?)",
            (inv.org_id, user_id, inv.role.value, inv.invited_by, time.time())
        )
        conn.commit()
        
        return Member(org_id=inv.org_id, user_id=user_id, role=inv.role)

    # ─── Audit Log ────────────────────────────────────────────────

    def log_event(self, org_id: str, user_id: str, action: str,
                  resource_type: str = None, resource_id: str = None,
                  details: dict = None, ip_address: str = None):
        event = AuditEvent(
            org_id=org_id, user_id=user_id, action=action,
            resource_type=resource_type, resource_id=resource_id,
            details=details, ip_address=ip_address
        )
        
        conn = self.db._get_conn()
        conn.execute(
            """INSERT INTO audit_log (org_id, user_id, action, resource_type, resource_id, details, ip_address, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.org_id, event.user_id, event.action, event.resource_type,
             event.resource_id, json.dumps(event.details), event.ip_address, event.timestamp)
        )
        conn.commit()

    def get_audit_log(self, org_id: str, limit: int = 100,
                     offset: int = 0, action: str = None) -> List[AuditEvent]:
        conn = self.db._get_conn()
        
        if action:
            rows = conn.execute(
                """SELECT * FROM audit_log WHERE org_id = ? AND action = ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (org_id, action, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM audit_log WHERE org_id = ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (org_id, limit, offset)
            ).fetchall()
        
        return [
            AuditEvent(
                org_id=r["org_id"], user_id=r["user_id"], action=r["action"],
                resource_type=r["resource_type"], resource_id=r["resource_id"],
                details=json.loads(r["details"]) if r["details"] else {},
                ip_address=r["ip_address"], timestamp=r["timestamp"]
            ) for r in rows
        ]

    # ─── API Keys ─────────────────────────────────────────────────

    def create_api_key(self, org_id: str, name: str, user_id: str = None,
                      scopes: List[str] = None) -> Tuple[str, str]:
        """Create API key. Returns (key_id, raw_key)."""
        key_id = f"ak_{secrets.token_hex(16)}"
        raw_key = f"mimo_{secrets.token_hex(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        conn = self.db._get_conn()
        conn.execute(
            """INSERT INTO api_keys (id, org_id, user_id, key_hash, name, scopes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key_id, org_id, user_id, key_hash, name, json.dumps(scopes or []), time.time())
        )
        conn.commit()
        
        return key_id, raw_key

    def verify_api_key(self, raw_key: str) -> Optional[Dict]:
        """Verify API key. Returns org info if valid."""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        conn = self.db._get_conn()
        row = conn.execute(
            """SELECT ak.*, o.name as org_name, o.plan as org_plan
               FROM api_keys ak
               JOIN organizations o ON ak.org_id = o.id
               WHERE ak.key_hash = ? AND ak.revoked = 0""",
            (key_hash,)
        ).fetchone()
        
        if not row:
            return None
        
        # Check expiry
        if row["expires_at"] and time.time() > row["expires_at"]:
            return None
        
        # Update last used
        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
            (time.time(), row["id"])
        )
        conn.commit()
        
        return {
            "key_id": row["id"],
            "org_id": row["org_id"],
            "org_name": row["org_name"],
            "org_plan": row["org_plan"],
            "user_id": row["user_id"],
            "name": row["name"],
            "scopes": json.loads(row["scopes"]),
        }

    def revoke_api_key(self, key_id: str) -> bool:
        conn = self.db._get_conn()
        conn.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))
        conn.commit()
        return True

    # ─── Helpers ──────────────────────────────────────────────────

    def _generate_slug(self, name: str) -> str:
        import re
        slug = name.lower().strip()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        
        # Ensure uniqueness
        conn = self.db._get_conn()
        base_slug = slug
        counter = 1
        while conn.execute("SELECT 1 FROM organizations WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        return slug

    def check_permission(self, org_id: str, user_id: str, action: str) -> bool:
        """Check if user has permission for action in organization."""
        member = self.get_member(org_id, user_id)
        if not member:
            return False
        return member.can(action)


# Singleton
_b2b_manager = None

def get_b2b_manager() -> B2BManager:
    global _b2b_manager
    if _b2b_manager is None:
        _b2b_manager = B2BManager()
    return _b2b_manager
