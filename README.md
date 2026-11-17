<div align="center">

<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />

  <h1>Built with AI Studio</h2>

  <p>The fastest path from prompt to production with Gemini.</p>

  <a href="https://aistudio.google.com/apps">Start building</a>

</div>

# TradeMind AI

AI-assisted quantitative research and **paper-trading** platform for crypto, stocks and forex.
Real-money trading is disabled by design: there is no live execution code.

## Quick start (Python 3.12)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e "backend[dev]"            # add [providers] for CCXT + yfinance
cd backend && pytest
uvicorn trademind.api.main:app --reload  # http://127.0.0.1:8000/docs
```

## Docs
- [Architecture audit](docs/ARCHITECTURE_AUDIT.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [External integrations register](docs/EXTERNAL_INTEGRATIONS.md)

Nothing here is financial advice, and no backtest result is evidence of future profit.
