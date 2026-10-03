"""Global super administrator — full platform access, non-deletable."""
from __future__ import annotations

import os

from ..core.security import hash_password, iso

SUPER_ADMIN_USER_ID = "user-super-admin"
SUPER_ADMIN_ROLE_ID = "role-super-administrator"
SUPER_ADMIN_MEMBERSHIP_ID = "membership-super-admin"


def super_admin_config() -> dict[str, str]:
    return {
        "username": os.getenv("SUPER_ADMIN_USERNAME", "Admin"),
        "password": os.getenv("SUPER_ADMIN_PASSWORD", "P@882w0rd"),
        "email": os.getenv("SUPER_ADMIN_EMAIL", "cacsmstraders@cacsms.com"),
    }


def ensure_super_admin(conn, tenant_id: str, now: str, permission_codes: list[str]) -> None:
    cfg = super_admin_config()
    conn.execute(
        "INSERT OR IGNORE INTO roles(id,tenant_id,name,description,created_at) VALUES(?,?,?,?,?)",
        (SUPER_ADMIN_ROLE_ID, tenant_id, "Super Administrator", "Global system root — all permissions", now),
    )
    for code in permission_codes:
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)",
            (SUPER_ADMIN_ROLE_ID, f"perm-{code}"),
        )

    row = conn.execute(
        "SELECT id FROM users WHERE id=? OR username=? COLLATE NOCASE",
        (SUPER_ADMIN_USER_ID, cfg["username"]),
    ).fetchone()
    pw_hash = hash_password(cfg["password"])
    if not row:
        conn.execute(
            """INSERT INTO users(id,username,email,password_hash,first_name,last_name,display_name,timezone,preferred_currency,status,is_platform_admin,is_system_protected,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                SUPER_ADMIN_USER_ID,
                cfg["username"],
                cfg["email"],
                pw_hash,
                "System",
                "Administrator",
                "Super Administrator",
                "Africa/Lagos",
                "USD",
                "ACTIVE",
                1,
                1,
                now,
                now,
            ),
        )
        uid = SUPER_ADMIN_USER_ID
    else:
        uid = row["id"]
        sync_pw = os.getenv("SUPER_ADMIN_SYNC_PASSWORD", "1").strip().lower() in ("1", "true", "yes")
        conn.execute(
            """UPDATE users SET username=?, email=?, display_name=?, is_platform_admin=1, is_system_protected=1, status='ACTIVE', updated_at=?"""
            + (", password_hash=?" if sync_pw else "")
            + " WHERE id=?",
            (
                (cfg["username"], cfg["email"], "Super Administrator", now, pw_hash, uid)
                if sync_pw
                else (cfg["username"], cfg["email"], "Super Administrator", now, uid)
            ),
        )

    conn.execute(
        "INSERT OR IGNORE INTO tenant_memberships(id,tenant_id,user_id,role_id,status,created_at) VALUES(?,?,?,?,?,?)",
        (SUPER_ADMIN_MEMBERSHIP_ID, tenant_id, uid, SUPER_ADMIN_ROLE_ID, "ACTIVE", now),
    )


def assert_user_mutable(conn, user_id: str, action: str = "modify") -> None:
    row = conn.execute("SELECT is_system_protected, username FROM users WHERE id=?", (user_id,)).fetchone()
    if row and int(row["is_system_protected"] or 0):
        from fastapi import HTTPException

        raise HTTPException(
            403,
            f"The system super administrator ({row['username']}) cannot be {action}.",
        )
