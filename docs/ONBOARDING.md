# Connecting Claude Desktop to Greenwood's PCO MCP Server

Five-minute setup per person. Each teammate authenticates with their own
Planning Center account, so what they can read/edit in Claude is exactly
what they can read/edit in PCO directly.

## Prerequisites

Before you start, you need:

- **Claude Desktop** installed — download from <https://claude.ai/download>
- **A Planning Center account** that's already been added to Greenwood's
  PCO organization. (If you're not sure, ask Justin or whoever runs the
  PCO admin.)

That's it. No Python, no command line, no editing config files.

## Step 1 — Get your personal session token

Each person needs their own session token. Don't share tokens; PCO sees
your actions as YOU.

1. In any browser, open <https://pco-mcp.greenwoodbc.net/auth/login>
2. Click **Connect with Planning Center →**
3. Sign in with your own PCO email + password
4. Click **Allow** to authorize Greenwood's AI Assistant
5. You'll land on a green page that says **"✓ Connected as [Your Name]"**
6. **Copy the session token** displayed on the page — it's a long UUID
   like `9077ff0c-0500-45e5-b603-310d78b4a293`. Paste it somewhere safe
   right now (password manager, encrypted note). You won't see it again
   unless you log in fresh.

> If you ever lose the token, just visit the same URL and log in
> again — that mints a fresh one. Your old token will keep working too,
> but you only really need one.

## Step 2 — Add the connector to Claude Desktop

In Claude Desktop:

1. Click your profile (bottom-left) → **Settings** (the gear icon)
2. Select **Connectors** in the sidebar
3. Click **Add custom connector**
4. Fill in the form:
   - **Name:** `Planning Center` (or any label you like)
   - **URL:** `https://pco-mcp.greenwoodbc.net/mcp`
   - **Authentication:** choose **Custom headers** (or "API key" → header form)
   - **Header name:** `X-Session-Token`
   - **Header value:** paste the UUID from Step 1
5. Click **Save** / **Connect**

The connector should immediately show as connected with a tool count
(should be **69 tools**).

## Step 3 — Restart and try it

1. **Fully quit Claude Desktop.** Right-click the icon in the Windows
   tray (or macOS menu bar) → **Quit**. Closing the window isn't enough.
2. Relaunch Claude Desktop.
3. Open a new chat.
4. Click the **tools icon** at the bottom of the message box (looks like
   a hammer or wrench). You should see **Planning Center** with 69 tools
   listed underneath.
5. Type:

   > List my Planning Center service types.

   You should get a real response with service types from Greenwood's
   PCO. Try a few more queries:

   > Show me the most recent plan in Weekend Service.
   >
   > List the songs scheduled this Sunday.
   >
   > Which volunteers are scheduled on the worship team next week?

## What you can and can't do

The server exposes the full Planning Center Services API — listing plans,
songs, teams, volunteers, plan items, song arrangements, and so on. It
also exposes write tools: create/update/delete plans, songs, blockouts,
team assignments, etc.

**Whether a specific action succeeds depends on YOUR Planning Center
permissions, not Claude's.** Examples:

- A volunteer with read-only access can list and view but can't create or
  edit anything — Claude will surface a "403 Forbidden" message with PCO's
  reason.
- A worship pastor with edit rights can create plans, schedule songs,
  assign volunteers, etc.
- An org admin can do everything the API allows.

If Claude says it can't do something, that's usually PCO saying no, not a
bug. Ask the PCO admin to grant you the permission if it's something you
need.

## Security and privacy

- **Your session token is personal.** Anyone with it can act as you in
  PCO. Treat it like a password. Don't paste it in shared chats or
  screenshots.
- **You can revoke your own access anytime** by visiting
  `https://pco-mcp.greenwoodbc.net/auth/logout/YOUR-TOKEN-HERE` (replace
  the placeholder). That deletes your session from the server. Your
  Planning Center account is unaffected.
- **Tokens last as long as you stay active.** Planning Center's refresh
  tokens expire after 90 days of complete inactivity. If you don't use
  the connector for 90+ days you'll be asked to log in again at the same
  URL.
- **The server admin can see who's connected** (name, email, last-used
  time) and can revoke any session.

## Troubleshooting

**The connector won't enable / shows 0 tools**
- Confirm you copied the WHOLE session token, no extra spaces.
- Check that the URL is exactly `https://pco-mcp.greenwoodbc.net/mcp`
  (with the `/mcp` on the end).
- Try `https://pco-mcp.greenwoodbc.net/health` in a browser — if that
  doesn't show `{"status":"ok"}`, the server is down; tell Justin.

**Claude says "session expired" or "please re-authenticate"**
- Your PCO refresh token aged out (90+ days inactive). Go to
  <https://pco-mcp.greenwoodbc.net/auth/login> and log in again; copy the
  fresh token; update it in the Claude Desktop connector settings.

**A specific tool returns "403 Forbidden"**
- That's PCO refusing the action based on your permissions. Not a bug.
- Ask the PCO admin to grant you the relevant role if you need the access.

**Tools icon shows other servers but not Planning Center**
- Restart Claude Desktop completely (Quit, relaunch). The Connectors UI
  only re-reads its state on launch.

**I'm on an older Claude Desktop that doesn't have a Connectors UI**
- Use the legacy config-file approach documented in
  [`docs/CLIENTS.md`](CLIENTS.md). That route needs Python + the
  `mcp-proxy` package on your machine.

## Who to ask for help

- **Justin Allison** (justin@greenwood.church) — server admin, can
  revoke sessions, troubleshoot any of the above.
