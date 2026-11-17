# External Integrations Assessment

Checked: 2026-11-17 (web research only; nothing was installed or executed). Star counts are approximate, from search/GitHub page snapshots. Where a value could not be observed it is marked "not observed". Licenses are as reported by the repository page in the snapshot; re-verify the LICENSE file before vendoring any code.

## Summary

| Tool | Source | License | Decision |
|---|---|---|---|
| day-trader-skill (11 Claude skills) | https://github.com/Jakeschincariol/day-trader-skill | MIT | Research only (concepts re-implemented; no skills installed; `trader-broker` excluded) |
| TradingAgents | https://github.com/TauricResearch/TradingAgents | Apache-2.0 | Research only (adapt architecture ideas; no runtime dependency) |
| GMGN OpenAPI / gmgn-skills | https://github.com/GMGNAI/gmgn-skills (docs: https://docs.gmgn.ai/index/gmgn-agent-api) | MIT | Approved with restrictions (read-only endpoints only; swap/cooking excluded) |
| Grok Bot (trading bots) | UNVERIFIED (no canonical repo; see section C) | n/a | Research only |
| MCP-Trading | UNVERIFIED (no project of that exact name found) | n/a | Rejected (unidentified; execution-capable MCP servers out of scope) |
| agent-kit | Candidates: https://github.com/sendaifun/solana-agent-kit, https://github.com/coinbase/agentkit (which one is meant: UNVERIFIED) | Apache-2.0 (both; Coinbase repo page labelled "Other") | Rejected (wallet/signing toolkits) |
| OpenTrade | https://github.com/OpenTradeOSS/OpenTrade (probable, unconfirmed) | Elastic License 2.0 | Rejected (macOS app, real-money Robinhood execution) |
| Jupiter API | https://developers.jup.ag/docs | Proprietary API terms | Approved with restrictions (quote/price/token data only) |
| Read-only chain data (public RPC, Etherscan V2, Sourcify, DexScreener, GoPlus) | see section C | Service terms | Approved with restrictions |
| Claude Code | https://code.claude.com/docs/en/skills | Proprietary (Anthropic terms) | Approved (dev workflow only, not runtime) |
| CCXT | https://github.com/ccxt/ccxt | MIT | Approved with restrictions (public market data only) |
| yfinance | https://github.com/ranaroussi/yfinance | Apache-2.0 | Approved with restrictions (research/dev data, not real-time grade) |

Unverified identities: Grok Bot (trading context), MCP-Trading, "agent-kit" (two plausible candidates), OpenTrade (probable match only).

---

## A. day-trader-skill (Claude Code skills)

- **Source:** https://github.com/Jakeschincariol/day-trader-skill (site: https://daytraderskill.com). Identity verified by exact skill-list match.
- **License:** MIT.
- **Activity (checked 2026-11-17):** created 2026-10-20; ~8.1k stars, ~1.9k forks, ~61 open issues; single contributor. Very new and star growth was very fast (a third-party post two days after creation cited 436 stars), so popularity is weak evidence of quality. Last-commit date not directly observed (an aggregator lists Oct 20, 2026).
- **Skills (11, from README):** trader-scanner (chart scanner), trader-news, trader-entry (entry timer), trader-exit (exit planner), trader-timemachine (outcome simulation), trader-risk, trader-budget (position sizing), trader-broker (order executor), trader-alerts, trader-analyst (earnings analyst), trader-pelosi ("Pelosi Tracker").
- **Dependencies:** Python standard library only (3.8+); no pip packages.
- **Data sources:** Yahoo Finance chart endpoints (query1/query2.finance.yahoo.com), Nasdaq Trader symbol directories, SEC EDGAR (requires a User-Agent with name and email), House Clerk disclosures. Free, unofficial, possibly lagging (README says so).
- **Security:** Skills run shell commands and bundled Python scripts (e.g. `scan.py`, ~47 KB) with network access. A third-party scan (qai.io) flagged no malicious patterns but states that is not proof of safety. `trader-broker` can send orders via a brokerage connector (README mentions Alpaca MCP) after an explicit "yes". Install is via `/plugin install` or copying folders into `~/.claude/skills`. We did not read the source.
- **API requirements:** none for data; broker keys only for trader-broker.
- **Terms:** Yahoo data is unofficial/personal-use; SEC EDGAR fair-access policy applies. README: not financial advice.
- **Compatibility:** These are Claude Code artifacts, not an importable library. Logic is stdlib Python, so concepts can be reimplemented in our FastAPI stack.
- **Decision: Research only.** Do not install the skills or run their scripts in the product. Reimplement useful concepts natively in tested modules. `trader-broker` is excluded (live execution is disabled). Pelosi Tracker data (congressional disclosures) is delayed (disclosure lag up to ~45 days), so at most a labelled, informational sentiment input.
- **Concepts we can implement ourselves:**
  - **ORB / session analysis:** compute the first N-minute (README example: 15 min) opening range high/low per session; trigger on a 5-minute close beyond the range; filter by session window, relative volume and a flat-by-close rule. Needs per-market session calendars (equities regular hours, FX sessions, crypto 24/7 with UTC anchors).
  - **Time Machine (historical scenario simulation):** replay or resample recent intraday bars (README: 10,000 simulated sessions from the prior ~59 sessions, fixed seed) to estimate stop/target hit odds. Implement as a seeded bootstrap/Monte Carlo in the backtest engine, report results as simulated distributions, never as predictions, and avoid look-ahead.
  - **Risk/budget/exit/alerts:** fixed-fraction sizing, stop and target defined before entry, alerts for stop/target/flat-by-close. These overlap with our deterministic Risk Engine; use as test cases, not code.

## B. TradingAgents

- **Source:** https://github.com/TauricResearch/TradingAgents (verified).
- **License:** Apache-2.0.
- **Activity (2026-11-17):** ~123k stars, 516 commits, latest listed release v0.7.1 (2026-10). Last-commit date not observed.
- **Architecture:** LangGraph pipeline: analyst team (fundamentals, sentiment, news, technical; run in parallel) -> bull and bear researchers debate -> Trader proposes -> risk-management agents -> Portfolio Manager approves/rejects.
- **Dependencies:** Python >= 3.11 (compatible with 3.12); `pip install .`; LangGraph/LangChain stack (full list not enumerated, large transitive tree); optional extras (e.g. Bedrock); local Ollama supported.
- **API requirements:** LLM provider key (OpenAI/Google/Anthropic etc.); optional Alpha Vantage, FRED, social-post screening keys.
- **Security:** Library only; no wallet or signing. Keys via environment variables. Large dependency surface and prompt-injection exposure from news/social text; pin and audit versions. Not reviewed at source level.
- **Terms:** Research use; README disclaims financial advice.
- **Compatibility:** OK on Python 3.12, WSL, likely Windows; 8 GB RAM fine with hosted LLMs, no GPU needed.
- **Decision: Research only.** Adapt the pattern (parallel analysts, bull/bear debate over one shared data snapshot, trader, risk gate, portfolio manager) behind our own Pydantic agent interfaces. Do not take LangGraph as a runtime dependency. Avoid its LLM-based risk step as the final gate: our deterministic Risk Engine decides, and an LLM can never override a rejection. Avoid copying its data-fetch tools wholesale.

## C. Crypto / GMGN ecosystem

### Grok Bot (trading context)
- **Identity: UNVERIFIED.** "Grok Bot" appears to be a bot-building feature of xAI's Grok with community trading bots (directories list ~235; tutorials describe an "8-agent crypto desk"). A separate 2025 "Grok on Telegram" announcement also exists. No single official repo, license or API contract was established; many promotional threads are scam-adjacent.
- **Decision: Research only.** Inspiration for multi-agent token due diligence (holder distribution, liquidity lock, sniper/insider detection). No integration.

### GMGN and gmgn-skills
- **Source:** https://github.com/GMGNAI/gmgn-skills (verified); homepage https://gmgn.ai/ai; API docs https://docs.gmgn.ai/index/gmgn-agent-api.
- **License:** MIT. **Activity:** created 2026-03-12, ~719 stars, 464 commits, 49 open issues, multiple contributors; last-commit date not observed.
- **Coverage:** Solana, BSC, Base, Ethereum (the demo key name also mentions Monad/Tron). Read-only skills: gmgn-token, gmgn-contract-dd, gmgn-holder-analysis, gmgn-market (kline, trending, new launches, search), gmgn-portfolio, gmgn-wallet-analysis/score/style/review, gmgn-track, gmgn-callout, gmgn-kline-pattern. Trade-capable: gmgn-swap and gmgn-cooking submit real swaps and limit/TP/SL orders (gmgn-token-buy hands off to swap).
- **Dependencies:** Node CLI (`npm i -g gmgn-cli` or `npx skills add GMGNAI/gmgn-skills`); Python/TypeScript sources. Node version not observed.
- **API requirements:** GMGN API key (apply at gmgn.ai/ai using an Ed25519 public key). `GMGN_PRIVATE_KEY` is an API request-signing key, not a wallet key, but it also authorises swaps; swaps need an IP whitelist; README says quotes need it on every chain. A public demo key exists for read-only testing. Rate limits not observed. Trading uses GMGN's hosted-wallet model.
- **Security:** Third-party closed service. Installing the whole skill pack gives an agent a path to submit trades. Credentials live in `~/.config/gmgn/.env`. Its analytics (smart money, KOL, bundlers) are vendor heuristics.
- **Terms:** Proprietary API terms at gmgn.ai; not reviewed in full.
- **Compatibility:** Call REST endpoints from Python via our own thin adapter (httpx); no Node needed; low RAM.
- **Decision: Approved with restrictions.** Optional read-only adapter for token/market/holder/wallet data with a GET-only endpoint allow-list; key in an environment variable; signing key never present in the app or any LLM context. Do not install gmgn-skills/gmgn-cli; swap/cooking are blocked.

### MCP-Trading
- **Identity: UNVERIFIED.** No project with that exact name was found. Searches returned unrelated MCP servers (e.g. bybit-exchange/trading-mcp, okx/agent-trade-kit, small CCXT-based "trading MCP" repos with near-zero stars). No URL is asserted.
- **Decision: Rejected** (unidentified). MCP servers exposing order placement are out of scope; a read-only market-data MCP could be reconsidered if an exact repo is named.

### agent-kit
- **Identity: UNVERIFIED which one.** Two plausible candidates:
  - **SendAI Solana Agent Kit**, https://github.com/sendaifun/solana-agent-kit: Solana-only, TypeScript/npm (v2.0.10), Apache-2.0, ~1.7k stars, 60+ protocol actions including Jupiter swaps and transfers; works with a wallet keypair. More plausible given the Solana/Jupiter/GMGN context.
  - **Coinbase AgentKit**, https://github.com/coinbase/agentkit: TypeScript and Python, wallet-agnostic, Ethereum/Base/Polygon/Arbitrum/Optimism plus Solana, ~1.4k stars, Apache-2.0 per LICENSE.md (GitHub label showed "Other"), 489 open issues; managed wallet needs Coinbase Developer Platform keys.
- **Security:** Both exist to give an agent a wallet and the ability to sign/submit transactions, which we forbid. Neither was source-audited.
- **Decision: Rejected.** Read-only needs are covered by the data sources below.

### OpenTrade
- **Identity: probable, not confirmed from the video:** https://github.com/OpenTradeOSS/OpenTrade ("open-source trading harness for Claude Code / Codex agents"; ~257 stars; created 2026-06-28; release v0.2.9 seen, Sep 2026). Same-named repos (brandononchain/opentrade, satinath-nit/OpenTrade.ai) are different projects.
- **License:** Elastic License 2.0 (source-available, not OSI open source; forbids offering it as a hosted service).
- **Details:** Apple-silicon macOS app (Windows/Linux only on an experimental branch); agents trade real Robinhood accounts via Robinhood's MCP; scheduled background agents.
- **Decision: Rejected.** Real-money execution, macOS-first, non-OSI license. Its guardrail/monitoring ideas can inform our design.

### Jupiter (Solana aggregator)
- **Source:** https://developers.jup.ag/docs (Swap API base `https://api.jup.ag/swap/v2`; limits at https://developers.jup.ag/docs/portal/rate-limits).
- **Observed:** Keyless 0.5 req/s (30/min); Free tier with API key 1 req/s (60/min); paid tiers higher. Swap V2 `GET /order` returns a routed quote plus a ready-to-sign transaction; `GET /build` returns instructions; `/execute` submits. Ultra V1 is deprecated in favour of Swap V2.
- **Security:** `/order` returns an unsigned transaction. We must never sign or execute it; use for quotes, routing and price-impact research only and discard the transaction payload.
- **Terms:** Proprietary API; review Jupiter's terms before any commercial use (personal use here).
- **Decision: Approved with restrictions.** Quote/price/token metadata only; no `/execute`, no signing, no wallet keys; keyless or free key from an environment variable; respect 0.5-1 RPS.

### Read-only chain data (Solana, Base, BSC, Ethereum)
| Source | Use | Terms / limits observed |
|---|---|---|
| Solana public RPC (https://solana.com/docs/references/clusters) | balances, accounts, `simulateTransaction` dry-runs | Public endpoints are rate-limited and not for production; 403/429 reports are common. Use a provider free tier for sustained use. |
| EVM RPC for Ethereum/Base/BSC | `eth_call`, `eth_getCode`, `eth_estimateGas` | Specific public endpoints not verified here; use provider free tiers; rate-limited. |
| Etherscan API V2 (https://docs.etherscan.io) | verified source/ABI, tx history across 50+ EVM chains, one key | Free: 3 calls/s, 100k/day, selected chains only (check https://docs.etherscan.io/supported-chains for Base/BSC coverage); free tier is personal/research use; key required; verified-source endpoints remain free for all tiers. |
| Sourcify (https://docs.sourcify.dev/docs/api/) | contract verification lookups | API v2 only (v1 turned off 2026-07-07); no key; single-contract fair use, no crawling. |
| DexScreener (https://docs.dexscreener.com/api/reference) | token discovery, pairs, liquidity, volume | No key; ~300 req/min pair/token endpoints, 60 req/min profile/boost endpoints; no historical OHLC. |
| GoPlus Security (https://docs.gopluslabs.io) | token risk flags (honeypot, proxy, open source) | Free, 30 calls/min; heuristic, can be wrong. |

- **Decision: Approved with restrictions** for all: read-only JSON-RPC methods and GET endpoints only (allow-list), no `sendTransaction`/`eth_sendRawTransaction`, no private keys anywhere, outputs labelled "observed data" vs "model interpretation", and heuristic risk flags never the sole basis for a proposal. Simulation (`simulateTransaction`/`eth_call`) only on hypothetical, unsigned payloads.

## D. Claude Code (development workflow)

- **Docs:** https://code.claude.com/docs/en/skills.
- **How it works:** A skill is a `SKILL.md` (YAML frontmatter plus Markdown) loaded on demand or invoked with `/skill-name`. Locations: personal `~/.claude/skills/<name>/`, project `.claude/skills/<name>/` (commit to share), enterprise managed settings, plugins. `CLAUDE.md` holds always-loaded project guidance; nested `CLAUDE.md` files scope guidance to subdirectories. Put procedures in skills and standing rules in `CLAUDE.md`.
- **Use here:** development-time only (inspect, refactor, generate/run tests, review); not a runtime dependency. Keep a project `CLAUDE.md` stating paper-only / no-signing rules. Do not install third-party skills (including day-trader-skill) into the dev environment without reading their scripts.
- **Decision: Approved** (development tooling under Anthropic's terms).

## E. CCXT and yfinance

### CCXT
- **Source:** https://github.com/ccxt/ccxt. **License:** MIT. **Activity:** ~44.9k stars (2026-11-17 snapshot), actively maintained; latest release date not observed.
- **Deps/compat:** Python 3.7+; pip install; works on 3.12 and Windows/WSL; modest RAM (loading markets per exchange is the main cost).
- **Security:** Library only, but private methods can place orders. Instantiate without credentials and wrap in a read-only adapter exposing OHLCV, tickers, order books and markets while blocking `create_order`, `withdraw` etc.
- **API/limits:** Public endpoints need no key; built-in leaky-bucket rate limiter (`enableRateLimit`); each exchange's own terms and geo-restrictions apply.
- **Decision: Approved with restrictions** (public market data only, no API keys).

### yfinance
- **Source:** https://github.com/ranaroussi/yfinance. **License:** Apache-2.0. **Activity:** ~25.9k stars; release date not observed.
- **Caveats:** Not affiliated with or endorsed by Yahoo; uses Yahoo's undocumented public endpoints; README says it is for research/educational use, that Yahoo's API is intended for personal use, and that users must check Yahoo's terms. Data may be delayed, adjusted, incomplete, rate-limited (HTTP 429) or break without notice. It is not institutional-grade or guaranteed real-time data. Intraday history depth is limited (verify current Yahoo limits before relying on it). Forex tickers (`EURUSD=X`) are indicative, not executable quotes.
- **Deps:** pandas, numpy, HTTP client libraries (README mentions optional `curl_cffi`); fine on Python 3.12.
- **Decision: Approved with restrictions.** Dev/research fallback behind the provider abstraction, with caching, backoff, staleness flags and an "unofficial/delayed data" label; never used to imply real-time execution realism.

---

## Policy

1. **No untrusted install scripts.** Do not run `npx skills add`, `npm i -g`, `curl | sh`, plugin installers or third-party repo scripts. Dependencies are added only after review and pinned.
2. **No credentials in code.** API keys come from environment variables / git-ignored `.env`; never logged and never placed in LLM prompts or tool outputs.
3. **Read-only on-chain.** Only allow-listed read methods and public data APIs; no wallet private keys or seed phrases anywhere in the system; transaction simulation only on unsigned, hypothetical payloads.
4. **No auto-signing or submission.** No blockchain transaction or live broker order may be signed or submitted; execution is paper-only. Anything exposing swap/order/execute (gmgn-swap, gmgn-cooking, Jupiter `/execute`, trader-broker, AgentKit / Solana Agent Kit, OpenTrade's Robinhood MCP) is excluded or blocked at the adapter layer.
5. **LLMs never override the deterministic Risk Engine.** Third-party signals and recommendations are inputs to validate, never trade instructions.
6. **No profitability claims** without verified backtest/paper evidence; star counts and promotional material are not evidence.
