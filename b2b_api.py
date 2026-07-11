"""
B2B API endpoints — REST API for organization management.

Endpoints:
- POST /api/org/create - Create organization
- GET /api/org/:id - Get organization
- GET /api/org/:id/members - List members
- POST /api/org/:id/invite - Invite member
- POST /api/org/accept-invite - Accept invitation
- GET /api/org/:id/audit - Audit log
- POST /api/org/:id/api-keys - Create API key
- POST /api/license/generate - Generate license key
- GET /api/admin/dashboard - Admin dashboard stats
"""

import json
import secrets
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from b2b import get_b2b_manager, Role


class LicenseManager:
    """License key generation and validation for B2B customers."""

    def __init__(self):
        self._licenses = {}

    def generate_license(self, org_id: str, plan: str = "starter", duration_days: int = 365) -> dict:
        key = f"lic_{secrets.token_hex(16)}"
        license_data = {
            "key": key,
            "org_id": org_id,
            "plan": plan,
            "created_at": time.time(),
            "expires_at": time.time() + (duration_days * 86400),
            "active": True,
        }
        self._licenses[key] = license_data
        return license_data

    def validate_license(self, key: str) -> dict:
        lic = self._licenses.get(key)
        if not lic:
            return None
        if not lic["active"]:
            return None
        if time.time() > lic["expires_at"]:
            lic["active"] = False
            return None
        return lic

    def revoke_license(self, key: str) -> bool:
        lic = self._licenses.get(key)
        if lic:
            lic["active"] = False
            return True
        return False

    def get_org_licenses(self, org_id: str) -> list:
        return [lic for lic in self._licenses.values() if lic["org_id"] == org_id]


_license_manager = LicenseManager()


def get_license_manager():
    return _license_manager


def create_b2b_handler(auth_manager):
    """Create B2B HTTP handler with auth."""

    class B2BHandler(BaseHTTPRequestHandler):
        
        def _get_user_from_token(self) -> dict:
            """Extract user from Authorization header."""
            auth_header = self.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return None
            
            token = auth_header[7:]
            return auth_manager.verify_token(token)

        def _send_json(self, data: dict, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        def _send_error(self, message: str, status: int = 400):
            self._send_json({"error": message}, status)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            
            user = self._get_user_from_token()
            if not user:
                return self._send_error("Unauthorized", 401)
            
            user_id = user.get("sub")
            b2b = get_b2b_manager()
            
            # ─── List User Organizations ──────────────────────
            if path == "/api/org/list":
                orgs = b2b.get_user_organizations(user_id)
                return self._send_json({"organizations": orgs})
            
            # ─── Get Organization ─────────────────────────────
            if path.startswith("/api/org/") and path.count("/") == 3:
                org_id = path.split("/")[3]
                
                if not b2b.check_permission(org_id, user_id, "projects.view"):
                    return self._send_error("Forbidden", 403)
                
                org = b2b.get_organization(org_id)
                if not org:
                    return self._send_error("Organization not found", 404)
                
                return self._send_json({"organization": org.to_dict()})
            
            # ─── List Members ─────────────────────────────────
            if path.endswith("/members"):
                org_id = path.split("/")[3]
                
                if not b2b.check_permission(org_id, user_id, "members.view"):
                    return self._send_error("Forbidden", 403)
                
                members = b2b.get_organization_members(org_id)
                return self._send_json({
                    "members": [
                        {
                            "user_id": m.user_id,
                            "role": m.role.value,
                            "joined_at": m.joined_at,
                        } for m in members
                    ]
                })
            
            # ─── Audit Log ────────────────────────────────────
            if path.endswith("/audit"):
                org_id = path.split("/")[3]
                
                if not b2b.check_permission(org_id, user_id, "audit.view"):
                    return self._send_error("Forbidden", 403)
                
                limit = int(params.get("limit", ["100"])[0])
                offset = int(params.get("offset", ["0"])[0])
                action_filter = params.get("action", [None])[0]
                
                events = b2b.get_audit_log(org_id, limit, offset, action_filter)
                return self._send_json({
                    "events": [e.to_dict() for e in events]
                })

            # ─── Admin Dashboard ──────────────────────────────
            if path == "/api/admin/dashboard":
                # Admin-only endpoint - requires org.manage permission
                orgs = b2b.get_user_organizations(user_id)
                is_admin = False
                for org_info in orgs:
                    if b2b.check_permission(org_info.get("id", ""), user_id, "org.manage"):
                        is_admin = True
                        break
                
                if not is_admin:
                    return self._send_error("Admin access required", 403)
                
                # Gather stats across all organizations
                total_orgs = 0
                total_members = 0
                total_api_keys = 0
                
                for org_info in orgs:
                    org_id = org_info.get("id", "")
                    org = b2b.get_organization(org_id)
                    if org:
                        total_orgs += 1
                        members = b2b.get_organization_members(org_id)
                        total_members += len(members)
                
                lic_mgr = get_license_manager()
                total_licenses = sum(1 for _ in lic_mgr._licenses.values())
                active_licenses = sum(1 for lic in lic_mgr._licenses.values() if lic.get("active"))
                
                dashboard_data = {
                    "summary": {
                        "total_organizations": total_orgs,
                        "total_members": total_members,
                        "total_licenses": total_licenses,
                        "active_licenses": active_licenses,
                    },
                    "organizations": [
                        {
                            "id": org_info.get("id"),
                            "name": org_info.get("name"),
                            "slug": org_info.get("slug"),
                            "plan": org_info.get("plan"),
                        }
                        for org_info in orgs
                    ],
                    "recent_activity": [],
                }
                
                # Add recent audit events from first org if available
                if orgs:
                    first_org_id = orgs[0].get("id", "")
                    recent_events = b2b.get_audit_log(first_org_id, limit=10)
                    dashboard_data["recent_activity"] = [e.to_dict() for e in recent_events]
                
                return self._send_json(dashboard_data)
            
            self._send_error("Not found", 404)

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            
            user = self._get_user_from_token()
            if not user:
                return self._send_error("Unauthorized", 401)
            
            user_id = user.get("sub")
            b2b = get_b2b_manager()
            
            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
            
            # ─── Create Organization ──────────────────────────
            if path == "/api/org/create":
                name = body.get("name")
                if not name:
                    return self._send_error("name required")
                
                plan = body.get("plan", "starter")
                org = b2b.create_organization(name, user_id, plan)
                
                b2b.log_event(org.id, user_id, "org.created", "organization", org.id)
                
                return self._send_json({"organization": org.to_dict()}, 201)
            
            # ─── Invite Member ────────────────────────────────
            if path.endswith("/invite"):
                org_id = path.split("/")[3]
                
                if not b2b.check_permission(org_id, user_id, "members.invite"):
                    return self._send_error("Forbidden", 403)
                
                email = body.get("email")
                role_str = body.get("role", "user")
                
                if not email:
                    return self._send_error("email required")
                
                try:
                    role = Role(role_str)
                except ValueError:
                    return self._send_error(f"Invalid role: {role_str}")
                
                invitation = b2b.create_invitation(org_id, email, role, user_id)
                
                b2b.log_event(org_id, user_id, "member.invited", "invitation", invitation.id,
                             {"email": email, "role": role_str})
                
                return self._send_json({
                    "invitation": {
                        "id": invitation.id,
                        "email": invitation.email,
                        "role": invitation.role.value,
                        "token": invitation.token,
                        "expires_at": invitation.expires_at,
                    }
                }, 201)
            
            # ─── Accept Invitation ────────────────────────────
            if path == "/api/org/accept-invite":
                token = body.get("token")
                if not token:
                    return self._send_error("token required")
                
                member = b2b.accept_invitation(token, user_id)
                if not member:
                    return self._send_error("Invalid or expired invitation", 404)
                
                b2b.log_event(member.org_id, user_id, "member.joined", "member", user_id)
                
                return self._send_json({
                    "member": {
                        "org_id": member.org_id,
                        "role": member.role.value,
                    }
                })
            
            # ─── Create API Key ───────────────────────────────
            if path.endswith("/api-keys"):
                org_id = path.split("/")[3]
                
                if not b2b.check_permission(org_id, user_id, "api_keys.manage"):
                    return self._send_error("Forbidden", 403)
                
                name = body.get("name")
                if not name:
                    return self._send_error("name required")
                
                key_id, raw_key = b2b.create_api_key(org_id, name, user_id)
                
                b2b.log_event(org_id, user_id, "api_key.created", "api_key", key_id,
                             {"name": name})
                
                return self._send_json({
                    "api_key": {
                        "id": key_id,
                        "key": raw_key,  # Only shown once!
                        "name": name,
                    }
                }, 201)
            
            # ─── Revoke API Key ───────────────────────────────
            if path.endswith("/revoke"):
                org_id = path.split("/")[3]
                key_id = body.get("key_id")
                
                if not b2b.check_permission(org_id, user_id, "api_keys.manage"):
                    return self._send_error("Forbidden", 403)
                
                b2b.revoke_api_key(key_id)
                
                b2b.log_event(org_id, user_id, "api_key.revoked", "api_key", key_id)
                
                return self._send_json({"status": "revoked"})
            
            # ─── Generate License Key ─────────────────────────
            if path == "/api/license/generate":
                org_id = body.get("org_id")
                if not org_id:
                    return self._send_error("org_id required")
                
                if not b2b.check_permission(org_id, user_id, "org.manage"):
                    return self._send_error("Forbidden", 403)
                
                plan = body.get("plan", "starter")
                duration_days = body.get("duration_days", 365)
                
                lic_mgr = get_license_manager()
                license_data = lic_mgr.generate_license(org_id, plan, duration_days)
                
                b2b.log_event(org_id, user_id, "license.generated", "license", license_data["key"],
                             {"plan": plan, "duration_days": duration_days})
                
                return self._send_json({"license": license_data}, 201)
            
            self._send_error("Not found", 404)

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    return B2BHandler
