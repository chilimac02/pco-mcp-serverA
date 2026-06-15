# Connecting AI Clients

This doc shows how to wire **Claude Desktop**, **Open WebUI**, and **ChatGPT Desktop**
to your running PCO MCP server. Each user authenticates once at `/auth/login`,
gets a session token, and pastes it into their client.

> The server passes each user's PCO token through unchanged — so PCO enforces
> per-user permissions. A volunteer with read-only access gets read-only
> results; a worship pastor with edit rights can create/update plans.

---

## Pre-flight (do this once, then move on to your client)

### 1. The server is reachable

```bash
curl http://localhost:8000/health
# -> {"status":"ok"}
```

If you're connecting from a different machine on your LAN, replace `localhost`
with your TrueNAS / dev box IP. Internet access goes through your reverse
proxy at `https://pco-mcp.greenwoodbc.net/mcp` once Phase 11 is done.

### 2. You have a session token

Each user gets a personal one by visiting `/auth/login` in a browser:

```
http://localhost:8000/auth/login   (or the public URL)
```

→ "Connect with Planning Center" → PCO login → grants access → success page
shows a UUID (e.g., `60374b24-f98c-434c-b2b2-d46ba77400fd`). **Save it.**

If you lose your token, just log in again — that mints a new one without
breaking your existing session.

### 3. Smoke-test the MCP endpoint from curl

This confirms the server + your session token + the transport all work,
independent of any AI client. Replace `<TOKEN>` with your session token:

```bash
# initialize
curl -i -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Session-Token: <TOKEN>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0.1"}}}'
```

You should see `HTTP/1.1 200 OK` plus an `mcp-session-id` header. If you get
401, the token is wrong; if you get 404, you hit the wrong path.

---

## Claude Desktop

**Auth style:** header (`X-Session-Token`). Cleanest of the three.

### Config file location

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Add this block

If the file doesn't exist yet, create it with just this content. If it already
has other MCP servers, merge under the existing `mcpServers` key.

```json
{
  "mcpServers": {
    "planning-center": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "X-Session-Token": "<YOUR_SESSION_TOKEN>"
      }
    }
  }
}
```

**Public URL form** (Phase 11 onward): change `url` to
`https://pco-mcp.greenwoodbc.net/mcp`.

### After saving

1. **Restart Claude Desktop** entirely (Quit, not just close the window — on
   Windows: right-click the tray icon → Quit, then relaunch).
2. Look at the bottom-right of the message box — you should see a tools icon
   showing **69 tools available** under "planning-center".
3. Ask Claude:
   > "Use planning-center to list my service types."

   Expected: a response naming Weekend Service, Special Service, Ignite
   Student Ministry, etc. — pulled live from your PCO.

### Known quirks

- **Tools icon shows 0**: usually means Claude Desktop can't reach the URL.
  Check `curl http://localhost:8000/health` from a separate terminal.
- **"Server disconnected" loop**: almost always a bad session token; the
  server returns 401 and Claude treats that as a disconnect. Re-login at
  `/auth/login` and update the token.
- **403 errors when calling a tool**: that's PCO refusing the operation
  based on your user's permissions, not a bug. The error message includes
  PCO's reason.

---

## Open WebUI

**Auth style:** depends on the version. Open WebUI's MCP support has shifted
over time; pick the path that matches what's installed.

### Path A — Native MCP (Open WebUI ≥ 0.5)

Newer Open WebUI builds added direct MCP HTTP support. In the admin panel:

1. **Settings → Connections → MCP Servers → Add MCP Server**
2. Fill in:
   - **Name:** `planning-center`
   - **URL:** `http://<server-host>:8000/mcp?token=<YOUR_SESSION_TOKEN>`
     *(query-param form — Open WebUI's UI doesn't always let you set arbitrary
     request headers, so the `?token=` fallback is the safer choice here)*
   - **Type:** Streamable HTTP / HTTP
3. **Save**, refresh chat.

Test by selecting a model that supports tools and asking:
> "What service types exist in Planning Center?"

### Path B — MCPO bridge (older Open WebUI, or if Path A fails)

[MCPO](https://github.com/open-webui/mcpo) wraps any MCP server as an OpenAPI
endpoint, which Open WebUI consumes as a "tool". Install mcpo on the same
machine as Open WebUI:

```bash
pipx install mcpo
# or: pip install mcpo
```

Run it pointing at the MCP server:

```bash
mcpo --port 8765 -- python -m httpx http://localhost:8000/mcp?token=<TOKEN>
```

(See mcpo's README for the exact invocation — the project's CLI surface
moves between releases.)

Then in Open WebUI:

1. **Settings → Tools → Add Tool**
2. Point at `http://<mcpo-host>:8765/openapi.json`
3. Save and refresh.

### Known quirks

- **Tools listed but never called**: model has to support tool calling. The
  small OSS models on Ollama (Llama 3 instruct etc.) often need explicit
  `tool_choice` hints; try a Claude/GPT-4 model first to confirm the wiring,
  then experiment with smaller models.
- **CORS preflight failures**: not applicable — Open WebUI runs server-side,
  it doesn't make browser-direct requests to /mcp.

---

## ChatGPT Desktop

**Auth style:** query parameter (`?token=`). ChatGPT Desktop's MCP support
came late and its custom-header handling is uneven across versions — the
query param is the safer default.

### Setup

1. Open **ChatGPT Desktop → Settings → Connectors / Tools → Add**
2. Choose the **MCP server** / **Custom connector** option (label varies by
   release).
3. URL: `http://<server-host>:8000/mcp?token=<YOUR_SESSION_TOKEN>`
   - Local: `http://localhost:8000/mcp?token=...`
   - Public (Phase 11): `https://pco-mcp.greenwoodbc.net/mcp?token=...`
4. Save / Enable / Connect.

The connector should turn green / show a tool count once it's reached the
server.

### Test

Start a new chat with the connector enabled:
> "Use the planning-center connector to show me my service types."

### Known quirks

- **Connector won't enable**: ChatGPT Desktop sometimes requires HTTPS for
  custom MCP URLs. If you can't get `http://localhost:8000` to attach, finish
  Phase 11 (reverse proxy + HTTPS) and use the public URL instead.
- **Tools listed but call errors**: ChatGPT Desktop sometimes drops Accept
  headers — if you see protocol errors in our server log, that's the
  cause. Workaround: the query-param URL works regardless; just confirm
  your token is correct.

---

## Troubleshooting matrix

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 missing_session_token` | No `X-Session-Token` header and no `?token=` query param | Add one of the two |
| `401 invalid_session_token` | Token doesn't match any row in SQLite | Re-login at `/auth/login`, get a fresh token |
| `401 session_refresh_failed` | PCO rejected the refresh (token age > 90d or revoked) | Re-login |
| `500 encryption_key_mismatch` | `ENCRYPTION_KEY` env var changed since the row was written | Restore the original key, or have everyone re-login |
| `403` on a tool call | PCO permissions — the user can't do that action | Working as intended; surface the message to the user |
| `404` from PCO | Resource doesn't exist or the user can't see it | Same — surface PCO's error |
| Server reports 200 but client says "no tools" | Restart the client; some MCP clients cache the empty tool list from a failed initial connect | Quit + relaunch |
| `Connection refused` from client | Server isn't running, or you've got the wrong URL/port | `curl http://<host>:8000/health` to confirm |
