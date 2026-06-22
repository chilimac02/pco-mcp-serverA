# Connecting Claude Desktop to Greenwood's PCO MCP Server

Five-minute setup per person. Each teammate authenticates with their own
Planning Center account, so what they can read/edit in Claude is exactly
what they can read/edit in PCO directly.

## Prerequisites

- **Claude Desktop** installed — download from <https://claude.ai/download>
- **A Planning Center account** that's already been added to Greenwood's
  PCO organization. (If you're not sure, ask Justin or whoever runs the
  PCO admin.)

No Python, no command line, no editing config files.

## Step 1 — Get your personal session token

1. In any browser, open <https://pco-mcp.greenwoodbc.net/auth/login>
2. Click **Connect with Planning Center →**
3. Sign in with your own PCO email + password
4. Click **Allow** to authorize Greenwood's AI Assistant
5. You'll land on a green page that says **"✓ Connected as [Your Name]"**
6. **Copy the session token** displayed on the page — it's a long UUID
   like `9077ff0c-0500-45e5-b603-310d78b4a293`. Paste it somewhere safe
   right now (password manager, encrypted note).

> If you lose the token, just visit the same URL and log in again — that
> mints a fresh one. Your old token also keeps working unless someone
> revokes it; you only need one active.

## Step 2 — Build your personal connector URL

Take the session token from Step 1 and paste it into the end of this URL,
replacing `YOUR_TOKEN_HERE`:

```
https://pco-mcp.greenwoodbc.net/mcp?token=YOUR_TOKEN_HERE
```

Example with a real token (yours will be different):

```
https://pco-mcp.greenwoodbc.net/mcp?token=9077ff0c-0500-45e5-b603-310d78b4a293
```

**Treat this URL like a password.** Don't share it, screenshot it, or
paste it into shared chats — it contains your personal session token.

## Step 3 — Add the connector to Claude Desktop

1. In Claude Desktop, click your profile (bottom-left) → **Settings**
2. Select **Connectors** in the sidebar
3. Click **Add custom connector**
4. Fill in the form:
   - **Name:** `Planning Center` (or any label you like)
   - **Remote MCP server URL:** paste the URL you built in Step 2 (the
     one ending in `?token=YOUR_TOKEN`)
   - **Advanced settings:** leave **OAuth Client ID** and **OAuth Client
     Secret** empty — we don't use those.
5. Click **Add**

The connector should appear in your list. Click on it to confirm it's
enabled, then check that the tool count shows **69 tools** (or similar)
once the connection initializes.

## Step 4 — Restart and try it

1. **Fully quit Claude Desktop.** Right-click the icon in the Windows
   tray (or macOS menu bar) → **Quit**. Closing the window isn't enough.
2. Relaunch Claude Desktop.
3. Open a new chat.
4. Click the **tools icon** at the bottom of the message box (looks like
   a hammer/wrench). You should see **Planning Center** listed.
5. Try a query:

   > List my Planning Center service types.

   You should get a real response. More to try:

   > Show me the most recent plan in Weekend Service.
   >
   > List the songs scheduled this Sunday.
   >
   > Which volunteers are scheduled on the worship team next week?

## What you can and can't do

The server exposes most of Planning Center across these modules:

- **Services** — plans, songs, arrangements, teams, volunteers, schedules
- **People** — directory search, household management, workflows, lists,
  custom fields, forms
- **Groups** — small groups, members, events, locations, tags
- **Calendar** — org-wide events, rooms/resources, bookings, conflicts
- **Check-Ins** — events, locations, programmatic check-ins, headcounts
- **Publishing** — sermon series and episodes (read-only)
- **Registrations** — signups, attendees, categories (read + light writes)

**Giving is intentionally not exposed** — payment data is sensitive enough
that we don't want it touched by general AI workflows.

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

- **Your connector URL contains your personal session token.** Anyone
  with that URL can act as you in PCO. Treat it like a password. Don't
  paste it in shared chats, screenshots, or anywhere a coworker or
  attacker could see.
- **You can revoke your own access anytime** by visiting
  `https://pco-mcp.greenwoodbc.net/auth/logout/YOUR-TOKEN-HERE` (replace
  the placeholder with your token). That deletes your session from the
  server. Your Planning Center account is unaffected.
- **Tokens last as long as you stay active.** Planning Center's refresh
  tokens expire after 90 days of complete inactivity. If you don't use
  the connector for 90+ days you'll be asked to log in again at the same
  URL — you'll then update the URL in your connector with the new token.
- **The server admin can see who's connected** (name, email, last-used
  time) at `https://pco-mcp.greenwoodbc.net/admin` and can revoke any
  session.

## Updating your token

If you ever need to swap your token (rotated, lost, expired, OR the
server's authorized PCO scopes changed and your old token doesn't cover
the new modules):

1. Visit <https://pco-mcp.greenwoodbc.net/auth/login> again and copy the
   new token from the success page.
2. In Claude Desktop → Settings → Connectors → click your Planning Center
   connector to edit it.
3. Replace the URL with one that has the new token at the end.
4. Save.

> If you set up the connector before People/Groups/Calendar/etc. were
> added (i.e., when only Services was wired up), your old token only has
> the `services` scope. Re-login at the URL above to mint a new token
> with full module coverage.

## Troubleshooting

**The connector adds but shows 0 tools / "failed to connect"**
- Check that the URL is exactly
  `https://pco-mcp.greenwoodbc.net/mcp?token=YOUR_TOKEN` — no typos, no
  trailing whitespace, the `?token=` literal in front of the UUID.
- Try `https://pco-mcp.greenwoodbc.net/health` in a browser — if that
  doesn't show `{"status":"ok"}`, the server is down; tell Justin.
- Try opening
  `https://pco-mcp.greenwoodbc.net/mcp?token=YOUR_TOKEN` directly in a
  browser; you should see a JSON response (probably 405 Method Not
  Allowed because browsers send GET — that's fine, it confirms the URL
  is reachable and your token is recognized).

**Claude says "session expired" or "please re-authenticate"**
- Your PCO refresh token aged out (90+ days inactive). Re-login at
  <https://pco-mcp.greenwoodbc.net/auth/login>, get the new token, and
  update your connector URL per "Updating your token" above.

**A specific tool returns "403 Forbidden"**
- That's PCO refusing the action based on your permissions. Not a bug.
- Ask the PCO admin to grant you the relevant role if you need access.

**Tools icon shows other servers but not Planning Center**
- Restart Claude Desktop completely (Quit, relaunch). The Connectors UI
  only refreshes its state on launch.

**I'm using a different AI client (Open WebUI, ChatGPT Desktop, etc.)**
- See [`docs/CLIENTS.md`](CLIENTS.md) for per-client setup notes.

## Who to ask for help

- **Justin Allison** (justin@greenwood.church) — server admin, can
  revoke sessions, troubleshoot any of the above.
