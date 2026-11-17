# Deployment (no Docker)

```
Browser ──HTTPS──▶ Vercel (React/Vite static build)
   │
   └──HTTPS / WSS──▶ Nginx (VPS, TLS via certbot) ──▶ Gunicorn + Uvicorn workers (127.0.0.1:8000)
                                                         ├── PostgreSQL (localhost)   ← persistence phase
                                                         └── Redis (localhost)        ← persistence phase
```

The frontend and backend are deployed separately. The Python backend never runs on Vercel.
Everything is **paper trading only**; the backend has no live-execution code path.

## 1. Local development — Windows PowerShell

Requires Python 3.12 (`py -3.12`) and Node.js 20+.

```powershell
git clone https://github.com/jalal-stack/nq.git trademind; cd trademind
# If script execution is blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\dev.ps1 setup   # .venv, backend deps, frontend deps, copies .env.example -> .env
.\scripts\dev.ps1 test    # backend tests
.\scripts\dev.ps1 api     # http://127.0.0.1:8000/docs   (health: /api/v1/health)
.\scripts\dev.ps1 web     # second terminal: http://localhost:5173
```

The frontend reads `VITE_API_BASE_URL` (see `frontend/.env.example`; defaults to `http://127.0.0.1:8000`).

## 2. Backend — Ubuntu VPS (22.04/24.04)

```bash
# System packages (PostgreSQL/Redis are installed now; the app starts using them in the persistence phase)
sudo apt update
sudo apt install -y python3.12 python3.12-venv nginx certbot python3-certbot-nginx postgresql redis-server git

# Service user and code
sudo useradd --system --create-home --home-dir /opt/trademind --shell /usr/sbin/nologin trademind
sudo -u trademind git clone https://github.com/jalal-stack/nq.git /opt/trademind/src
sudo -u trademind ln -s /opt/trademind/src/backend /opt/trademind/backend
sudo -u trademind mkdir -p /opt/trademind/var
sudo -u trademind python3.12 -m venv /opt/trademind/.venv
sudo -u trademind /opt/trademind/.venv/bin/pip install "/opt/trademind/src/backend[server,providers]"

# Configuration (secrets live only here, readable by root and the service)
sudo mkdir -p /etc/trademind
sudo cp /opt/trademind/src/.env.example /etc/trademind/trademind.env
sudo nano /etc/trademind/trademind.env   # set TRADEMIND_CORS_ORIGINS=https://<your-app>.vercel.app
sudo chown root:trademind /etc/trademind/trademind.env && sudo chmod 640 /etc/trademind/trademind.env

# systemd
sudo cp /opt/trademind/src/deploy/systemd/trademind-api.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now trademind-api
curl -s http://127.0.0.1:8000/api/v1/health

# Nginx + HTTPS (edit server_name first)
sudo cp /opt/trademind/src/deploy/nginx/trademind-api.conf /etc/nginx/sites-available/trademind-api
sudo sed -i 's/api.example.com/api.YOUR-DOMAIN/g' /etc/nginx/sites-available/trademind-api
sudo ln -s /etc/nginx/sites-available/trademind-api /etc/nginx/sites-enabled/
# Get the certificate before enabling the 443 block, e.g. temporarily with only the :80 server:
sudo certbot certonly --nginx -d api.YOUR-DOMAIN
sudo nginx -t && sudo systemctl reload nginx

# Firewall
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

Gunicorn binds to `127.0.0.1:8000` only, so the API is reachable solely through Nginx.
`deploy/systemd/trademind-api.service` runs it as the unprivileged `trademind` user with a
read-only filesystem except `/opt/trademind/var` and a 2 GB memory cap (fits an 8 GB VPS).

Updating:

```bash
sudo -u trademind git -C /opt/trademind/src pull
sudo -u trademind /opt/trademind/.venv/bin/pip install "/opt/trademind/src/backend[server,providers]"
sudo systemctl restart trademind-api && journalctl -u trademind-api -n 50 --no-pager
```

## 3. Frontend — Vercel

1. Import the GitHub repository in Vercel.
2. **Root Directory:** `frontend` (framework preset Vite is picked up from `frontend/vercel.json`).
3. **Environment variable:** `VITE_API_BASE_URL=https://api.YOUR-DOMAIN` (Production and Preview).
4. Deploy, then add the Vercel URL to `TRADEMIND_CORS_ORIGINS` on the VPS and restart the service.

`VITE_*` variables are compiled into public JavaScript: never put API keys or secrets there.
Preview deployments get different URLs; add the ones you use to `TRADEMIND_CORS_ORIGINS`.

## 4. Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Status, `mode: paper_only`, `live_execution_enabled: false` |
| GET | `/api/v1/config` | Starting equity and risk limits |
| GET | `/api/v1/market/{provider}/ohlcv` | Candles + data-quality report (`synthetic`, `ccxt`, `yfinance`) |
| POST | `/api/v1/risk/evaluate` | Deterministic risk decision for a trade proposal |
| POST | `/api/v1/backtest` | Baseline strategy backtest |
| WS | `/api/v1/ws/market` | Candle snapshot, then periodic updates (polled from the provider) |

OpenAPI docs: `/docs`.
