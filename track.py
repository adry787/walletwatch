"""Wallet Watch - Crypto portfolio tracker and price monitor."""

import os
import json
import time
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class TokenHolding:
    symbol: str
    name: str
    balance: float
    price_usd: float = 0.0
    value_usd: float = 0.0
    contract_address: str = ""
    chain: str = "ethereum"

    def update_value(self):
        self.value_usd = self.balance * self.price_usd


@dataclass
class PriceAlert:
    symbol: str
    target_price: float
    condition: str  # "above" or "below"
    triggered: bool = False
    created_at: float = field(default_factory=time.time)

    def check(self, current_price: float) -> bool:
        if self.triggered:
            return False
        if self.condition == "above" and current_price >= self.target_price:
            self.triggered = True
            return True
        if self.condition == "below" and current_price <= self.target_price:
            self.triggered = True
            return True
        return False


class PriceFeed:
    """Fetch token prices from CoinGecko API."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    TOKEN_IDS = {
        "ETH": "ethereum", "BTC": "bitcoin", "USDT": "tether",
        "BNB": "binancecoin", "MATIC": "matic-network", "ARB": "arbitrum",
        "USDC": "usd-coin", "SOL": "solana", "AVAX": "avalanche-2",
        "LINK": "chainlink", "UNI": "uniswap", "AAVE": "aave",
        "DAI": "dai", "SHIB": "shiba-inu", "DOGE": "dogecoin",
    }

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        if not HAS_REQUESTS:
            logger.warning("requests not installed, using mock prices")
            return {s: 0.0 for s in symbols}

        ids = [self.TOKEN_IDS.get(s.upper(), s.lower()) for s in symbols]
        try:
            resp = requests.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            result = {}
            for sym, token_id in zip(symbols, ids):
                if token_id in data:
                    result[sym.upper()] = data[token_id].get("usd", 0.0)
                else:
                    result[sym.upper()] = 0.0
            return result
        except Exception as e:
            logger.error("Price fetch failed: %s", e)
            return {s: 0.0 for s in symbols}

    def get_token_info(self, symbol: str) -> dict:
        if not HAS_REQUESTS:
            return {}
        token_id = self.TOKEN_IDS.get(symbol.upper(), symbol.lower())
        try:
            resp = requests.get(
                f"{self.BASE_URL}/coins/{token_id}",
                params={"localization": "false", "tickers": "false",
                        "community_data": "false", "developer_data": "false"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            market = data.get("market_data", {})
            return {
                "name": data.get("name", symbol),
                "symbol": symbol.upper(),
                "price_usd": market.get("current_price", {}).get("usd", 0),
                "market_cap": market.get("market_cap", {}).get("usd", 0),
                "volume_24h": market.get("total_volume", {}).get("usd", 0),
                "price_change_24h": market.get("price_change_percentage_24h", 0),
                "price_change_7d": market.get("price_change_percentage_7d", 0),
            }
        except Exception as e:
            logger.error("Token info fetch failed: %s", e)
            return {}


class WalletTracker:
    """Track wallet balances and portfolio value."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.holdings: dict[str, dict[str, TokenHolding]] = {}
        self.alerts: list[PriceAlert] = []
        self.price_feed = PriceFeed()
        os.makedirs(data_dir, exist_ok=True)

    def add_holding(self, wallet: str, symbol: str, balance: float,
                    chain: str = "ethereum") -> TokenHolding:
        wallet = wallet.lower()
        if wallet not in self.holdings:
            self.holdings[wallet] = {}

        holding = TokenHolding(
            symbol=symbol.upper(),
            name=symbol,
            balance=balance,
            chain=chain,
        )
        self.holdings[wallet][f"{chain}:{symbol.upper()}"] = holding
        self._update_prices(wallet)
        return holding

    def _update_prices(self, wallet: str) -> None:
        wallet = wallet.lower()
        if wallet not in self.holdings:
            return

        symbols = list(set(h.symbol for h in self.holdings[wallet].values()))
        prices = self.price_feed.get_prices(symbols)

        for key, holding in self.holdings[wallet].items():
            if holding.symbol in prices:
                holding.price_usd = prices[holding.symbol]
                holding.update_value()

    def get_portfolio_value(self, wallet: str) -> dict:
        wallet = wallet.lower()
        self._update_prices(wallet)

        holdings = self.holdings.get(wallet, {})
        total_value = sum(h.value_usd for h in holdings.values())

        items = []
        for key, h in sorted(holdings.items(), key=lambda x: x[1].value_usd, reverse=True):
            items.append({
                "symbol": h.symbol,
                "chain": h.chain,
                "balance": h.balance,
                "price_usd": h.price_usd,
                "value_usd": h.value_usd,
                "allocation": (h.value_usd / total_value * 100) if total_value > 0 else 0,
            })

        return {
            "wallet": wallet,
            "total_value_usd": round(total_value, 2),
            "holdings": items,
            "token_count": len(holdings),
        }

    def add_alert(self, symbol: str, target_price: float, condition: str = "above") -> PriceAlert:
        alert = PriceAlert(symbol=symbol.upper(), target_price=target_price, condition=condition)
        self.alerts.append(alert)
        logger.info("Alert set: %s %s $%.2f", symbol, condition, target_price)
        return alert

    def check_alerts(self) -> list[dict]:
        triggered = []
        symbols = list(set(a.symbol for a in self.alerts if not a.triggered))
        if not symbols:
            return []

        prices = self.price_feed.get_prices(symbols)
        for alert in self.alerts:
            if alert.symbol in prices and alert.check(prices[alert.symbol]):
                triggered.append({
                    "symbol": alert.symbol,
                    "target": alert.target_price,
                    "current": prices[alert.symbol],
                    "condition": alert.condition,
                })
                logger.warning("ALERT: %s is now $%.2f (%s $%.2f)",
                               alert.symbol, prices[alert.symbol],
                               alert.condition, alert.target_price)
        return triggered

    def get_token_report(self, symbol: str) -> dict:
        info = self.price_feed.get_token_info(symbol)
        if not info:
            return {"error": f"Could not fetch info for {symbol}"}
        return info

    def save_portfolio(self, wallet: str, path: str = None) -> str:
        wallet = wallet.lower()
        if path is None:
            path = os.path.join(self.data_dir, f"portfolio_{wallet[:10]}.json")

        portfolio = self.get_portfolio_value(wallet)
        with open(path, "w") as f:
            json.dump(portfolio, f, indent=2)
        return path


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Wallet Watch - Crypto Tracker")
    parser.add_argument("--wallet", type=str, help="Wallet address to track")
    parser.add_argument("--chain", type=str, default="ethereum")
    parser.add_argument("--token", type=str, help="Get info for a token")
    parser.add_argument("--alert", type=str, nargs=3,
                        metavar=("SYMBOL", "above/below", "PRICE"),
                        help="Set price alert")
    args = parser.parse_args()

    tracker = WalletTracker()

    if args.token:
        report = tracker.get_token_report(args.token)
        print(json.dumps(report, indent=2))
    elif args.alert:
        symbol, condition, price = args.alert
        tracker.add_alert(symbol, float(price), condition)
        print(f"Alert set: {symbol} {condition} ${price}")
    elif args.wallet:
        tracker.add_holding(args.wallet, "ETH", 1.5, args.chain)
        tracker.add_holding(args.wallet, "USDC", 1000, args.chain)
        portfolio = tracker.get_portfolio_value(args.wallet)
        print(json.dumps(portfolio, indent=2))
    else:
        print("Usage: python track.py --wallet 0x... or --token ETH")
