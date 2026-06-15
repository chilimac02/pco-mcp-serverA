"""End-to-end verification for the Phase 10 admin page.

Checks:
  1. GET /admin with no auth                       -> 401 + WWW-Authenticate
  2. GET /admin with wrong creds                   -> 401
  3. GET /admin with correct creds                 -> 200 + live session listed
  4. POST /admin/sessions/{token}/revoke (good)    -> 303 to /admin
                                                    + session deleted from DB
  5. (re-)login by creating a throwaway session    -> ensures we don't break
     directly via the OAuth callback path is too                    the real one
     complex; instead we just hit /auth/login UI to verify the page comes back
     up with the expected layout (no row for the revoked session).

To leave you logged in, the script creates a synthetic test session row,
revokes that one, and never touches your real session.
"""

from __future__ import annotations

import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.auth import crypto
from app.config import DB_PATH


BASE = "http://127.0.0.1:8000"
ADMIN_USER = "admin"
ADMIN_PASS = "change-me-before-going-public"


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def passed(msg):
    print(f"[OK] {msg}")


def insert_test_session() -> str:
    """Drop a synthetic session row in so revoke tests don't touch real data."""
    token = f"verify-phase10-{uuid.uuid4()}"
    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                session_token, pco_user_id, pco_user_name, pco_user_email,
                access_token, refresh_token, token_expires, scopes,
                created_at, last_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token,
                "9999999",
                "ZZZ Phase 10 Verify",
                "verify@example.com",
                crypto.encrypt("fake_access_token"),
                crypto.encrypt("fake_refresh_token"),
                now + 3600,
                "services",
                now,
                now,
            ),
        )
        conn.commit()
    return token


def row_exists(token: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT 1 FROM sessions WHERE session_token = ?", (token,))
        return cur.fetchone() is not None


def main():
    fake_token = insert_test_session()
    print(f"Inserted synthetic session: {fake_token[:24]}...")

    # ----- 1. No auth -> 401 -------------------------------------------
    r = httpx.get(f"{BASE}/admin", timeout=10.0)
    if r.status_code != 401:
        fail(f"#1 expected 401 without auth, got {r.status_code}")
    if "www-authenticate" not in {k.lower() for k in r.headers}:
        fail(f"#1 missing WWW-Authenticate header: {dict(r.headers)}")
    passed("no auth -> 401 + WWW-Authenticate")

    # ----- 2. Wrong creds -> 401 ---------------------------------------
    r = httpx.get(f"{BASE}/admin", auth=("nope", "wrong"), timeout=10.0)
    if r.status_code != 401:
        fail(f"#2 expected 401 with bad creds, got {r.status_code}")
    passed("bad creds -> 401")

    # ----- 3. Right creds -> 200 + sees the synthetic row --------------
    r = httpx.get(f"{BASE}/admin", auth=(ADMIN_USER, ADMIN_PASS), timeout=10.0)
    if r.status_code != 200:
        fail(f"#3 expected 200 with creds, got {r.status_code}\n{r.text[:500]}")
    if fake_token not in r.text:
        fail(f"#3 dashboard didn't include the synthetic token")
    if "ZZZ Phase 10 Verify" not in r.text:
        fail(f"#3 dashboard didn't include synthetic user name")
    # Count <tr> rows to confirm the table is rendered.
    body_rows = len(re.findall(r"<tr>", r.text))
    passed(f"good creds -> 200, dashboard renders {body_rows} <tr> rows including the synthetic session")

    # ----- 4. Revoke synthetic session ---------------------------------
    r = httpx.post(
        f"{BASE}/admin/sessions/{fake_token}/revoke",
        auth=(ADMIN_USER, ADMIN_PASS),
        follow_redirects=False,
        timeout=10.0,
    )
    if r.status_code != 303:
        fail(f"#4 expected 303 redirect, got {r.status_code}\n{r.text[:500]}")
    if r.headers.get("location") != "/admin":
        fail(f"#4 unexpected redirect target: {r.headers.get('location')}")
    if row_exists(fake_token):
        fail(f"#4 synthetic session still present after revoke")
    passed(f"revoke -> 303 to /admin, row deleted from DB")

    # ----- 5. Dashboard no longer shows the revoked row ----------------
    r = httpx.get(f"{BASE}/admin", auth=(ADMIN_USER, ADMIN_PASS), timeout=10.0)
    if fake_token in r.text:
        fail("#5 dashboard still mentions the revoked token after refresh")
    passed("dashboard no longer mentions the revoked synthetic session")

    # ----- 6. Revoke non-existent -> 404 -------------------------------
    r = httpx.post(
        f"{BASE}/admin/sessions/does-not-exist/revoke",
        auth=(ADMIN_USER, ADMIN_PASS),
        follow_redirects=False,
        timeout=10.0,
    )
    if r.status_code != 404:
        fail(f"#6 expected 404 revoking missing session, got {r.status_code}")
    passed("revoke unknown token -> 404")

    print("\nAll Phase 10 checks passed.")


if __name__ == "__main__":
    main()
