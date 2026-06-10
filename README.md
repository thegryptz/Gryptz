# Gryptz

**AI-Powered Solana DEX Scanner** — autonomous AI that scans trending Solana tokens every 2 minutes, scores each one 0–100 using DeepInfra LLM, and alerts you via Telegram before you ape.

[![CI](https://github.com/GryptzDev/Gryptz/actions/workflows/ci.yml/badge.svg)](https://github.com/GryptzDev/Gryptz/actions)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What it does

Gryptz runs a continuous scan loop:

1. **Scans** trending Solana tokens from DexScreener (pump.fun, Raydium, Orca)
2. **Filters** by liquidity, volume, and buy ratio — removing obvious garbage
3. **Scores** each token with DeepInfra AI — rug risk, momentum, verdict
4. **Alerts** via Telegram when score ≥ 60

### Gryptz Score

| Score | Meaning |
|-------|---------|
| 80–100 | Strong signal — solid liquidity, momentum, low rug risk |
| 60–79 | Worth watching |
| 40–59 | Neutral, mixed signals |
| 0–39 | Avoid |

---

## Quick Start

**Prerequisites:** Python 3.11+, Telegram bot token, DeepInfra API key

```bash
git clone https://github.com/GryptzDev/Gryptz.git
cd Gryptz
pip install -r requirements.txt
cp .env.example .env   # fill in your tokens
python main.py
```

### Docker

```bash
cp .env.example .env
docker-compose up -d
```

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/score <CA>` | Score any Solana token on-demand |
| `/top` | Top signals from last scan |
| `/help` | Help |

---

## Configuration

```env
TELEGRAM_BOT_TOKEN=...      # from @BotFather
DEEPINFRA_API_KEY=...       # from deepinfra.com
TELEGRAM_CHAT_ID=...        # chat to send auto-alerts (optional)
SCAN_INTERVAL=120           # seconds between scans
MIN_GRYPTZ_SCORE=60         # alert threshold
MIN_LIQUIDITY_USD=5000      # liquidity filter
MIN_VOLUME_1H_USD=10000     # 1h volume filter
MIN_BUY_RATIO=0.55          # buy pressure filter
```

---

## Architecture

```
Scanner Loop (every 2 min)
  └─ DexScreener API → filter → DeepInfra AI → Score
         ↓
  Telegram Bot
  ├─ Auto alerts (score ≥ MIN_GRYPTZ_SCORE)
  └─ On-demand: /score <CA>
```

---

## Development

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE)

---

_Not financial advice. DYOR._
