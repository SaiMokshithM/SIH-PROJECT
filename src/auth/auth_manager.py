"""
src/auth/auth_manager.py
========================
Role-Based Access Control (RBAC) and Session Management
for the AI Border Surveillance Command Center & Authority Portal.

Roles:
- OPERATOR: Standard surveillance monitoring, camera controls, detections.
- HIGHER_AUTHORITY: Executive surveillance overview, incident dossiers,
                    evidence repository, incident acknowledge/resolve, audit logs.
- AGENCY_ADMIN: Full administrative and authority clearance.
"""

import time
import secrets
from typing import Optional, Dict, Any
from fastapi import HTTPException, Header, Depends

# ── Role Definitions ──────────────────────────────────────────────────────────

class UserRole:
    OPERATOR = "OPERATOR"
    HIGHER_AUTHORITY = "HIGHER_AUTHORITY"
    AGENCY_ADMIN = "AGENCY_ADMIN"


# Default credentials / PINs for SIH demonstration & agency deployment
AUTHORITY_CREDENTIALS = {
    "commander": {
        "pin": "9926",
        "name": "Col. Rajesh Sharma",
        "role": UserRole.HIGHER_AUTHORITY,
        "badge": "BSF-HQ-091",
        "department": "Border Surveillance Command",
    },
    "agency_admin": {
        "pin": "9926",
        "name": "Chief Security Director",
        "role": UserRole.AGENCY_ADMIN,
        "badge": "AGENCY-DIR-01",
        "department": "Ministry of Home Affairs",
    },
    "operator": {
        "pin": "1234",
        "name": "Surveillance Operator #1",
        "role": UserRole.OPERATOR,
        "badge": "OP-FIELD-404",
        "department": "Border Outpost Unit 4",
    },
}

# In-memory active session tokens: token -> session dict
_ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_EXPIRY_SECONDS = 24 * 3600  # 24 hours


class AuthManager:
    """Manages role-based authentication and secure session tokens."""

    @staticmethod
    def authenticate(username_or_pin: str, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Authenticate by username + PIN, or directly by Authority PIN.
        Returns user info dictionary if valid, else None.
        """
        u = username_or_pin.strip().lower()
        p = pin.strip() if pin else None

        # Check direct PIN login (e.g. entering "9926")
        if not p and u in ("9926", "admin9926"):
            user_data = AUTHORITY_CREDENTIALS["commander"]
            return AuthManager._create_session(user_data, "commander")

        # Check username + PIN lookup
        if u in AUTHORITY_CREDENTIALS:
            cred = AUTHORITY_CREDENTIALS[u]
            if p is None or cred["pin"] == p:
                return AuthManager._create_session(cred, u)

        # Fallback quick demo PIN match
        if p == "9926" or u == "9926":
            user_data = AUTHORITY_CREDENTIALS["commander"]
            return AuthManager._create_session(user_data, "commander")

        return None

    @staticmethod
    def _create_session(cred: Dict[str, Any], username: str) -> Dict[str, Any]:
        token = f"auth_{secrets.token_hex(24)}"
        session_info = {
            "token": token,
            "username": username,
            "name": cred["name"],
            "role": cred["role"],
            "badge": cred["badge"],
            "department": cred["department"],
            "issued_at": time.time(),
            "expires_at": time.time() + SESSION_EXPIRY_SECONDS,
        }
        _ACTIVE_SESSIONS[token] = session_info
        return session_info

    @staticmethod
    def validate_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Validate session token and check expiry."""
        if not token:
            return None
        # Handle "Bearer <token>" format
        if token.startswith("Bearer "):
            token = token[7:].strip()

        session = _ACTIVE_SESSIONS.get(token)
        if not session:
            return None

        if time.time() > session.get("expires_at", 0):
            _ACTIVE_SESSIONS.pop(token, None)
            return None

        return session

    @staticmethod
    def revoke_token(token: str) -> bool:
        if token.startswith("Bearer "):
            token = token[7:].strip()
        if token in _ACTIVE_SESSIONS:
            del _ACTIVE_SESSIONS[token]
            return True
        return False


def get_current_authority(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces HIGHER_AUTHORITY or AGENCY_ADMIN role.
    Raises 401 / 403 HTTPException if invalid or insufficient clearance.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization token required for Higher Authority access."
        )

    session = AuthManager.validate_token(authorization)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired security clearance token."
        )

    role = session.get("role")
    if role not in (UserRole.HIGHER_AUTHORITY, UserRole.AGENCY_ADMIN):
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Higher Authority clearance level required."
        )

    return session
