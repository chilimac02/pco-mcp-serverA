"""Admin page routes.

  GET  /admin                                -> HTML table of all sessions
  POST /admin/sessions/{session_token}/revoke -> delete session, 303 back to /admin

Auth is HTTP Basic via `require_admin`. Token columns are NEVER rendered —
`token_store.list_sessions()` excludes them, so a screenshot of the page
can't leak credentials.
"""

from __future__ import annotations

import html
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin.auth import require_admin
from app.auth import token_store


router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# GET /admin — session list
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    _user: Annotated[str, Depends(require_admin)],
) -> HTMLResponse:
    sessions = await token_store.list_sessions()
    return HTMLResponse(_render_dashboard(sessions))


# ---------------------------------------------------------------------------
# POST /admin/sessions/{session_token}/revoke
# ---------------------------------------------------------------------------

@router.post("/sessions/{session_token}/revoke")
async def admin_revoke(
    session_token: str,
    _user: Annotated[str, Depends(require_admin)],
) -> RedirectResponse:
    deleted = await token_store.delete_session(session_token)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session with token starting '{session_token[:8]}…'",
        )
    # 303 = See Other; the browser follows with a GET back to the dashboard.
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _render_dashboard(sessions: list[dict]) -> str:
    now = int(time.time())
    rows = "".join(_render_row(s, now) for s in sessions) or _empty_row()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PCO MCP — Admin</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
    h1 {{ font-size: 1.5rem; }}
    .muted {{ color: #666; font-size: 0.9rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.95rem; }}
    th, td {{ text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid #eee;
             vertical-align: top; }}
    th {{ background: #fafafa; font-weight: 600; color: #555; }}
    tr:hover td {{ background: #f7f9fc; }}
    .token {{ font-family: ui-monospace, monospace; font-size: 0.85em;
              color: #444; }}
    .badge {{ display: inline-block; padding: 0.15rem 0.5rem; background: #eef;
              border-radius: 4px; font-size: 0.8em; color: #335; }}
    form.revoke {{ display: inline; margin: 0; }}
    button.revoke {{ background: #c62828; color: white; border: none;
                     padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer;
                     font-size: 0.85rem; }}
    button.revoke:hover {{ background: #a01818; }}
    .empty {{ text-align: center; color: #999; padding: 2rem 0; }}
  </style>
</head>
<body>
  <h1>PCO MCP — Connected sessions</h1>
  <p class="muted">{len(sessions)} session(s). Revoking a session forces the user to
     log in again at <code>/auth/login</code> to get a new token; their PCO
     account is not affected.</p>
  <table>
    <thead>
      <tr>
        <th>User</th>
        <th>PCO ID</th>
        <th>Scopes</th>
        <th>Last used</th>
        <th>Created</th>
        <th>Token expires</th>
        <th>Session token</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>"""


def _render_row(s: dict, now: int) -> str:
    safe_name = html.escape(s.get("pco_user_name") or "(no name)")
    safe_email = html.escape(s.get("pco_user_email") or "")
    safe_uid = html.escape(str(s.get("pco_user_id") or ""))
    safe_scopes = html.escape(s.get("scopes") or "")
    safe_token = html.escape(s["session_token"])

    name_block = f"{safe_name}"
    if safe_email:
        name_block += f"<br><span class='muted'>{safe_email}</span>"

    return f"""
      <tr>
        <td>{name_block}</td>
        <td class="muted">{safe_uid}</td>
        <td><span class="badge">{safe_scopes}</span></td>
        <td>{_fmt_relative(s.get("last_used"), now)}</td>
        <td>{_fmt_relative(s.get("created_at"), now)}</td>
        <td>{_fmt_token_expiry(s.get("token_expires"), now)}</td>
        <td class="token">{safe_token}</td>
        <td>
          <form class="revoke" method="post"
                action="/admin/sessions/{safe_token}/revoke"
                onsubmit="return confirm('Revoke session for {safe_name}?');">
            <button type="submit" class="revoke">Revoke</button>
          </form>
        </td>
      </tr>"""


def _empty_row() -> str:
    return """<tr><td colspan="8" class="empty">No connected sessions yet. Have a user visit <code>/auth/login</code>.</td></tr>"""


def _fmt_relative(ts: int | None, now: int) -> str:
    """Render '2 hours ago' / 'in 5 minutes'. Returns dash for None."""
    if ts is None:
        return "—"
    delta = int(ts) - now
    abs_d = abs(delta)
    if abs_d < 60:
        unit, n = "sec", abs_d
    elif abs_d < 3600:
        unit, n = "min", abs_d // 60
    elif abs_d < 86400:
        unit, n = "hr", abs_d // 3600
    else:
        unit, n = "day", abs_d // 86400
    label = f"{n} {unit}{'s' if n != 1 else ''}"
    return f"in {label}" if delta > 0 else f"{label} ago" if delta < 0 else "just now"


def _fmt_token_expiry(ts: int | None, now: int) -> str:
    """Highlight tokens nearing PCO expiry — useful for spotting stale sessions."""
    if ts is None:
        return "—"
    remaining = int(ts) - now
    rel = _fmt_relative(ts, now)
    if remaining < 0:
        return f"<span style='color:#c62828'>{rel} (expired)</span>"
    if remaining < 300:
        return f"<span style='color:#e65100'>{rel}</span>"
    return rel
