# Wallet Watch 👀

Real-time cryptocurrency portfolio tracker with price alerts, transaction monitoring, and portfolio analytics across multiple chains.

## Features

- Multi-chain support (Ethereum, BSC, Polygon, Arbitrum)
- Real-time price feeds via CoinGecko/CoinMarketCap
- Custom price alerts via Telegram/Discord
- Portfolio PnL tracking
- Historical performance charts

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add API keys
python track.py --wallet 0xYourAddress --chain ethereum
```

## GPU Requirements

| Component | GPU | VRAM | Notes |
|-----------|-----|------|-------|
| All operations | None | — | CPU/network only |
