# PCO MCP Server

Multi-user OAuth MCP server for Planning Center Services. Lets multiple users
connect their own Planning Center accounts to AI clients (Claude Desktop,
Open WebUI, ChatGPT Desktop) — each user's permissions are enforced by PCO.

Self-hosted, deployed via Docker on TrueNAS Scale / Portainer.

## Status

Built phase-by-phase per the project plan.

| Phase | Description | Status |
|---|---|---|
| 0 | Register OAuth app in PCO portal | done (manual) |
| 1 | Project scaffolding (FastAPI + FastMCP skeleton, SQLite schema) | done |
| 2 | OAuth `/auth/login` + `/auth/callback` (PKCE) | done |
| 3 | Token storage (Fernet encryption + auto-refresh) | done |
| 4 | MCP middleware (session token via header or query param) | done |
| 5 | Proof-of-concept tools (`get_me`, `list_service_types`) | done |
| 6 | Full read tools (~24 tools) | done |
| 7 | Full write tools (~41 tools) | done |
| 8 | Dockerfile + docker-compose | done |
| 9 | Test with three target clients | docs done (see [docs/CLIENTS.md](docs/CLIENTS.md)) |
| 10 | Admin page | todo |
| 11 | HTTPS + internet access (future) | todo |

**Tool count:** 69 MCP tools covering the Planning Center Services API.

## Local development

```bash
# 1. Copy .env.example to .env and fill in values
cp .env.example .env

# 2. Generate the two secrets:
#    ENCRYPTION_KEY — DO NOT change once data is stored
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#    SESSION_SECRET
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 3. Install deps in a virtual env
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 4. Run
uvicorn app.main:app --reload --port 8000

# 5. Confirm it's alive
curl http://localhost:8000/health
# → {"status":"ok"}
```

## Connecting an AI client

Each user authenticates at `http://<server>/auth/login`, gets a session
token, and pastes it into their AI client's MCP config. See
[**docs/CLIENTS.md**](docs/CLIENTS.md) for step-by-step setup of:

- **Claude Desktop** (uses `X-Session-Token` header)
- **Open WebUI** (native MCP or via the mcpo bridge)
- **ChatGPT Desktop** (uses `?token=` query parameter)

The same doc has a troubleshooting matrix for the common 401/403/timeout
errors.

## Docker / Portainer deployment

### Build and run with docker-compose

```bash
# Edit .env first (PCO credentials + generated secrets per "Local development" above)
docker compose up --build -d

# Confirm it booted
curl http://localhost:8000/health

# Watch logs
docker compose logs -f
```

### TrueNAS Scale (Portainer Stack + Cloudflare Tunnel)

The production stack runs **two services** in one Docker network: the `pco-mcp`
app and a `cloudflared` daemon that pulls inbound HTTPS through a Cloudflare
Tunnel. This avoids exposing your home IP, port-forwarding 443 on your router,
or running a separate Let's Encrypt reverse proxy.

1. **Create the host dataset** for SQLite, e.g.
   `/mnt/<pool>/apps/pco-mcp/db` (TrueNAS Apps → Storage → Add dataset).
   Update the volume path in `docker-compose.yml` to match your pool name.

2. **Create the Cloudflare Tunnel** (one-time):
   - Cloudflare → Zero Trust dashboard → Networks → Tunnels → Add tunnel
   - Choose Cloudflared, give it a name, copy the tunnel token
   - Public Hostnames tab: subdomain `pco-mcp`, domain `greenwoodbc.net`,
     service `HTTP` → `pco-mcp:8000`
   - Save. Cloudflare auto-creates the `pco-mcp.greenwoodbc.net` DNS record.

3. **Portainer → Stacks → Add stack → Repository**:
   - Repository URL: this repo on GitHub
   - Compose path: `docker-compose.yml`
   - Environment variables: every key from `.env.example`, including
     `CLOUDFLARE_TUNNEL_TOKEN` from step 2 and
     `PCO_REDIRECT_URI=https://pco-mcp.greenwoodbc.net/auth/callback`.
   - Deploy. Portainer builds the `pco-mcp` image and starts both services.

4. **Confirm the PCO OAuth app** has
   `https://pco-mcp.greenwoodbc.net/auth/callback` as a registered redirect URI
   (this was added in Phase 0).

5. **Verify** by hitting `https://pco-mcp.greenwoodbc.net/health` from
   anywhere on the internet.

### Volume layout inside the container

```
/app/                     # app code (read-only at runtime)
/app/db/                  # SQLite + Fernet-encrypted sessions  ← BIND-MOUNT THIS
/app/db/pco_sessions.db   # the live database
```

### Healthcheck

The Dockerfile installs no extra tools — the healthcheck uses Python's stdlib
`urllib.request` to hit `/health` every 30s.

### Security notes

- Runs as non-root user `pco` (uid 1000) inside the container.
- `.env` is read at runtime via `env_file`; it is **not** baked into the image
  (`.dockerignore` excludes it).
- Fernet ciphertext at rest survives image upgrades because the `db/` volume
  is on the host. **Never change `ENCRYPTION_KEY` after first run** — every
  stored token becomes unreadable and every user has to re-authenticate.
