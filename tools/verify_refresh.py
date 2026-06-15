"""One-off verification script for Phase 3 token auto-refresh.

Run as:  python tools/verify_refresh.py

What it does:
  1. Reads the (single) session row from SQLite, prints the encrypted
     access_token excerpt + Unix expiry timestamp.
  2. Decrypts and prints the access_token prefix (proves Fernet roundtrip).
  3. Manually backs token_expires up to (now - 60), simulating an expired token.
  4. Calls token_store.get_session_with_fresh_token() — should trigger a refresh.
  5. Confirms:
       - new access_token is different from the previously-decrypted one
       - new token_expires is ~7200s in the future
       - decrypting the freshly-stored ciphertext still works
  6. Smoke-tests the new token by hitting /services/v2/me on PCO.

Cleans up nothing — leaves the refreshed session valid for Phase 4 use.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from pathlib import Path

# Make `app` importable when run from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.auth import crypto, oauth, token_store
from app.config import DB_PATH


async def main() -> None:
    # ----- Step 1: snapshot the row before any change ------------------
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sessions LIMIT 1").fetchone()
    if row is None:
        sys.exit("No session in DB — run the OAuth flow first.")

    session_token = row["session_token"]
    print(f"Session under test: {session_token}")
    print(f"On-disk access_token excerpt: {row['access_token'][:48]}...")

    decrypted_before = crypto.decrypt(row["access_token"])
    print(f"Decrypted access_token excerpt: {decrypted_before[:24]}... (len={len(decrypted_before)})")
    print(f"Original token_expires: {row['token_expires']}  (in {row['token_expires'] - int(time.time())}s)")

    # ----- Step 2: force expiry ----------------------------------------
    fake_expiry = int(time.time()) - 60
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE sessions SET token_expires = ? WHERE session_token = ?",
            (fake_expiry, session_token),
        )
        conn.commit()
    print(f"\n-> Forced token_expires to {fake_expiry} (60s in the past)")

    # ----- Step 3: trigger auto-refresh --------------------------------
    print("-> Calling get_session_with_fresh_token() ...")
    fresh = await token_store.get_session_with_fresh_token(session_token)
    assert fresh is not None, "Session vanished mid-refresh?"

    decrypted_after = fresh["access_token"]
    print(f"\nDecrypted access_token AFTER refresh: {decrypted_after[:24]}... (len={len(decrypted_after)})")
    print(f"token_expires AFTER refresh: {fresh['token_expires']}  "
          f"(in {fresh['token_expires'] - int(time.time())}s)")

    # ----- Step 4: assertions ------------------------------------------
    if decrypted_before == decrypted_after:
        sys.exit("FAIL: access_token did not change after refresh.")
    if fresh["token_expires"] - int(time.time()) < 3600:
        sys.exit("FAIL: refreshed token_expires too close to now (<1hr).")
    print("\n[OK] access_token rotated")
    print("[OK] token_expires extended (>1hr remaining)")

    # ----- Step 5: confirm storage was re-encrypted --------------------
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row_after = conn.execute(
            "SELECT access_token FROM sessions WHERE session_token = ?",
            (session_token,),
        ).fetchone()
    on_disk = row_after["access_token"]
    if not on_disk.startswith("gAAAAA"):
        sys.exit("FAIL: refreshed token wasn't stored encrypted.")
    if "pco_tok_" in on_disk:
        sys.exit("FAIL: plaintext leak in stored ciphertext.")
    print("[OK] refreshed token re-encrypted on disk (no plaintext leak)")

    # Sanity: decrypting the on-disk value gives back what we got from the
    # helper. (Caught an early bug where we returned the encrypted form.)
    if crypto.decrypt(on_disk) != decrypted_after:
        sys.exit("FAIL: round-trip mismatch between in-memory and on-disk.")
    print("[OK] on-disk ciphertext round-trips to the same access_token")

    # ----- Step 6: smoke-test the fresh token against PCO --------------
    print("\n-> Smoke-testing the fresh access_token against /services/v2/me ...")
    try:
        profile = await oauth.fetch_user_profile(access_token=decrypted_after)
    except httpx.HTTPStatusError as exc:
        sys.exit(f"FAIL: PCO rejected the refreshed token: {exc.response.status_code} {exc.response.text}")

    attrs = profile.get("data", {}).get("attributes", {})
    name = attrs.get("full_name") or attrs.get("name") or "?"
    print(f"[OK] PCO accepted refreshed token; user = {name}")

    print("\nAll Phase 3 checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
