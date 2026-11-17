<div align="center">

<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />

  <h1>Built with AI Studio</h2>

  <p>The fastest path from prompt to production with Gemini.</p>

  <a href="https://aistudio.google.com/apps">Start building</a>

</div>

# TradeMind AI

AI-assisted quantitative research and **paper-trading** platform for crypto, stocks and forex.
Real-money trading is disabled by design: there is no live execution code.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI app (`trademind`): market data, indicators, risk engine, paper broker, backtester |
| `frontend/` | React + TypeScript + Vite + Tailwind dashboard (deployed to Vercel) |
| `deploy/` | systemd unit and Nginx config for the Ubuntu VPS |
| `scripts/dev.ps1` | Windows PowerShell setup / test / run helper |

No Docker is used anywhere.

## Quick start

Windows PowerShell:

```powershell
.\scripts\dev.ps1 setup
.\scripts\dev.ps1 api    # http://127.0.0.1:8000/docs
.\scripts\dev.ps1 web    # http://localhost:5173 (second terminal)
```

Linux / macOS:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"            # add ,providers for CCXT + yfinance
(cd backend && pytest)
(cd backend && uvicorn trademind.api.main:app --reload)
(cd frontend && npm install && npm run dev)
```

## Docs
- [Deployment: Vercel + Ubuntu VPS](docs/DEPLOYMENT.md)
- [Architecture audit](docs/ARCHITECTURE_AUDIT.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [External integrations register](docs/EXTERNAL_INTEGRATIONS.md)
- [Integrating the local MVP](docs/MVP_INTEGRATION.md)

Nothing here is financial advice, and no backtest result is evidence of future profit.
