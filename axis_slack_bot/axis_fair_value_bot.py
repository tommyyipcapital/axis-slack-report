#!/usr/bin/env python3
"""Daily Slack fair-value report for an Axis sUSDx position on Plasma."""

from __future__ import annotations

import argparse
import datetime as dt
import ssl
import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from zoneinfo import ZoneInfo

getcontext().prec = 50

DEFAULT_RPC_URL = "https://rpc.plasma.to"
DEFAULT_TOKEN_ADDRESS = "0x13a099765b34b3aafedb8698cf7fd418e7730012"
DEFAULT_WALLET_ADDRESS = "0x332bc14667a9d6d27f816b75a018ba1acc242bd2"
DEFAULT_RATE_CONTRACT_ADDRESS = "0x24891f7852021413d4acb0641994d045eeadc9be"
DEFAULT_SUSDX_PER_USDX = Decimal("0.995")
DEFAULT_USDX_USD = Decimal("1")
DEFAULT_RATE_DECIMALS = 18
DEFAULT_INITIAL_BALANCE_USDT = Decimal("1000000")
DEFAULT_STAKE_START_DATE = "2026-05-06"
DEFAULT_REPORT_TIMEZONE = "Asia/Hong_Kong"

try:
    import certifi
except ImportError:  # pragma: no cover - only used on very minimal Python installs.
    certifi = None


def env_decimal(name: str, default: Decimal) -> Decimal:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return Decimal(value.strip())


def clean_address(address: str) -> str:
    address = address.strip().lower()
    if address.startswith("0x"):
        address = address[2:]
    if len(address) != 40:
        raise ValueError(f"Expected a 20-byte address, got {address!r}")
    return address


def rpc_call(rpc_url: str, method: str, params: list[object]) -> str:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    context = None
    if certifi is not None:
        context = ssl.create_default_context(cafile=certifi.where())

    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        body = json.loads(response.read().decode("utf-8"))

    if "error" in body:
        raise RuntimeError(body["error"])
    return body["result"]


def eth_call(rpc_url: str, to_address: str, data: str) -> str:
    return rpc_call(
        rpc_url,
        "eth_call",
        [{"to": "0x" + clean_address(to_address), "data": data}, "latest"],
    )


def read_decimals(rpc_url: str, token_address: str) -> int:
    # decimals()
    return int(eth_call(rpc_url, token_address, "0x313ce567"), 16)


def read_balance(rpc_url: str, token_address: str, wallet_address: str) -> Decimal:
    # balanceOf(address)
    encoded_wallet = clean_address(wallet_address).rjust(64, "0")
    raw_balance = int(eth_call(rpc_url, token_address, "0x70a08231" + encoded_wallet), 16)
    decimals = read_decimals(rpc_url, token_address)
    return Decimal(raw_balance) / (Decimal(10) ** decimals)


def read_susdx_usdx_rate(
    rpc_url: str, rate_contract_address: str, rate_decimals: int
) -> Decimal:
    # getRate(), currently the live sUSDx/USDx fair-value rate contract.
    raw_rate = int(eth_call(rpc_url, rate_contract_address, "0x679aefce"), 16)
    return Decimal(raw_rate) / (Decimal(10) ** rate_decimals)


def money(value: Decimal) -> str:
    cents = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${cents:,.2f}"


def signed_money(value: Decimal) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{money(abs(value))}"


def number(value: Decimal, places: str = "0.000001") -> str:
    rounded = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return f"{rounded:,.6f}"


def decimal_places(value: Decimal, places: str) -> str:
    rounded = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return f"{rounded:f}"


def days_since(start_date: str, today: dt.date) -> int:
    start = dt.date.fromisoformat(start_date)
    return max((today - start).days, 0)


def projected_apy(net_change: Decimal, initial_balance: Decimal, days_staked: int) -> str:
    if days_staked == 0:
        return "N/A (day 0)"
    apy = (net_change / initial_balance) * (Decimal(365) / Decimal(days_staked))
    percent = (apy * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "+" if percent >= 0 else ""
    return f"{sign}{percent}%"


def build_message(
    balance: Decimal,
    susdx_usdx_rate: Decimal,
    usdx_usd: Decimal,
    rate_source: str,
    initial_balance_usdt: Decimal,
    stake_start_date: str,
    report_timezone: str,
) -> str:
    usdx_amount = balance * susdx_usdx_rate
    fair_value = usdx_amount * usdx_usd
    net_change = fair_value - initial_balance_usdt
    today_date = dt.datetime.now(ZoneInfo(report_timezone)).date()
    today = today_date.strftime("%Y-%m-%d")
    days_staked = days_since(stake_start_date, today_date)

    return "\n".join(
        [
            f"Axis - {today}",
            "==========================",
            f"Balance: {number(balance)} sUSDx",
            f"Value (USDT): {money(fair_value)}",
            f"Initial balance (USDT): {money(initial_balance_usdt)}",
            f"Net change: {signed_money(net_change)}",
            f"Projected APY: {projected_apy(net_change, initial_balance_usdt, days_staked)}",
            "",
            f"Days staked: {days_staked}",
            f"Live rate: 1 sUSDx = {decimal_places(susdx_usdx_rate, '0.000001')} USDx",
            f"Rate source: {rate_source}",
        ]
    )


def post_to_slack(webhook_url: str, message: str) -> None:
    payload = json.dumps({"text": message}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    context = None
    if certifi is not None:
        context = ssl.create_default_context(cafile=certifi.where())

    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        if response.status >= 300:
            raise RuntimeError(f"Slack returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report an Axis sUSDx wallet's fair value to Slack."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print only; do not post.")
    args = parser.parse_args()

    rpc_url = os.getenv("PLASMA_RPC_URL", DEFAULT_RPC_URL)
    token_address = os.getenv("SUSDX_TOKEN_ADDRESS", DEFAULT_TOKEN_ADDRESS)
    wallet_address = os.getenv("AXIS_WALLET_ADDRESS", DEFAULT_WALLET_ADDRESS)
    rate_contract_address = os.getenv(
        "SUSDX_USDX_RATE_CONTRACT_ADDRESS", DEFAULT_RATE_CONTRACT_ADDRESS
    )
    rate_decimals = int(os.getenv("SUSDX_USDX_RATE_DECIMALS", DEFAULT_RATE_DECIMALS))
    usdx_usd = env_decimal("USDX_USD", DEFAULT_USDX_USD)
    initial_balance_usdt = env_decimal(
        "INITIAL_BALANCE_USDT", DEFAULT_INITIAL_BALANCE_USDT
    )
    stake_start_date = os.getenv("STAKE_START_DATE", DEFAULT_STAKE_START_DATE)
    report_timezone = os.getenv("REPORT_TIMEZONE", DEFAULT_REPORT_TIMEZONE)

    balance = read_balance(rpc_url, token_address, wallet_address)
    susdx_usdx_rate = read_susdx_usdx_rate(
        rpc_url, rate_contract_address, rate_decimals
    )
    message = build_message(
        balance,
        susdx_usdx_rate,
        usdx_usd,
        rate_source=rate_contract_address,
        initial_balance_usdt=initial_balance_usdt,
        stake_start_date=stake_start_date,
        report_timezone=report_timezone,
    )

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if args.dry_run or not webhook_url:
        print(message)
        if not webhook_url and not args.dry_run:
            print("\nSLACK_WEBHOOK_URL is not set, so no Slack message was sent.")
        return 0

    post_to_slack(webhook_url, message)
    print("Slack report sent.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (urllib.error.URLError, RuntimeError, ValueError, InvalidOperation) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
