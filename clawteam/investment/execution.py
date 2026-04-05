"""Execution adapters for preview and policy-gated order routing."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib import error, parse, request

from pydantic import BaseModel, Field

from clawteam.investment.models import ExecutionMode


class OrderIntent(BaseModel):
    broker: str
    symbol: str
    side: str
    order_type: str = "LIMIT"
    quantity: Decimal = Decimal("0")
    quote_amount: Decimal | None = None
    price: Decimal | None = None
    market: str = "spot"
    time_in_force: str = "GTC"
    fractional: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderPreview(BaseModel):
    broker: str
    mode: ExecutionMode
    request: dict[str, Any]
    command: list[str] = Field(default_factory=list)
    endpoint: str = ""
    warnings: list[str] = Field(default_factory=list)


@dataclass
class BinanceCredentials:
    api_key: str
    api_secret: str
    base_url: str


class BinanceExecutionAdapter:
    """Small Binance Spot REST adapter with preview/test/live support."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
    ):
        self.credentials = BinanceCredentials(
            api_key=api_key or os.environ.get("BINANCE_API_KEY", ""),
            api_secret=api_secret or os.environ.get("BINANCE_API_SECRET", ""),
            base_url=base_url or os.environ.get("BINANCE_BASE_URL", "https://demo-api.binance.com"),
        )

    def _endpoint(self, path: str) -> str:
        normalized_base = self.credentials.base_url.rstrip("/")
        if normalized_base.endswith("/api"):
            normalized_base = normalized_base[:-4]
        return f"{normalized_base}{path}"

    @staticmethod
    def _timestamp(metadata: dict[str, Any]) -> int:
        timestamp = metadata.get("timestamp")
        if timestamp in (None, "", 0, "0"):
            return int(time.time() * 1000)
        return int(timestamp)

    def _signed_params(self, params: dict[str, Any]) -> str:
        encoded = parse.urlencode(params, doseq=True)
        signature = hmac.new(
            self.credentials.api_secret.encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{encoded}&signature={signature}"

    def preview_order(self, intent: OrderIntent, live: bool = False) -> OrderPreview:
        endpoint_url = self._endpoint("/api/v3/order" if live else "/api/v3/order/test")
        params: dict[str, Any] = {
            "symbol": intent.symbol,
            "side": intent.side.upper(),
            "type": intent.order_type.upper(),
            "timestamp": self._timestamp(intent.metadata),
        }
        if intent.quantity:
            params["quantity"] = str(intent.quantity)
        if intent.quote_amount is not None:
            params["quoteOrderQty"] = str(intent.quote_amount)
        if intent.price is not None:
            params["price"] = str(intent.price)
            params["timeInForce"] = intent.time_in_force
        warnings = [
            "Binance Demo Mode mirrors live features, but realistic market data is not equal to real fills.",
        ]
        if endpoint_url.startswith("https://api.binance.com/"):
            warnings.append(
                "Live Binance endpoint configured. Human approval is strongly recommended."
            )
        return OrderPreview(
            broker="binance",
            mode=ExecutionMode.live if live else ExecutionMode.preview,
            request=params,
            endpoint=endpoint_url,
            warnings=warnings,
        )

    def submit_order(self, intent: OrderIntent, live: bool = False) -> dict[str, Any]:
        if not self.credentials.api_key or not self.credentials.api_secret:
            raise RuntimeError("BINANCE_API_KEY and BINANCE_API_SECRET are required")
        preview = self.preview_order(intent, live=live)
        body = self._signed_params(preview.request)
        req = request.Request(
            preview.endpoint,
            data=body.encode("utf-8"),
            headers={"X-MBX-APIKEY": self.credentials.api_key},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network path
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Binance API HTTP error: {exc.code} {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network path
            raise RuntimeError(f"Binance API connection error: {exc}") from exc


class TossInvestExecutionAdapter:
    """Wrapper around tossctl preview/place workflows."""

    def __init__(self, executable: str = "tossctl"):
        self.executable = executable

    def build_preview_command(self, intent: OrderIntent) -> list[str]:
        command = [
            self.executable,
            "order",
            "preview",
            "--symbol",
            intent.symbol,
            "--side",
            intent.side.lower(),
            "--qty",
            str(intent.quantity),
            "--output",
            "json",
        ]
        if intent.market:
            command.extend(["--market", intent.market])
        if intent.fractional:
            command.append("--fractional")
        if intent.quote_amount is not None:
            command.extend(["--amount", str(intent.quote_amount)])
        if intent.price is not None:
            command.extend(["--price", str(intent.price)])
        return command

    def build_execute_command(self, intent: OrderIntent, confirm_token: str) -> list[str]:
        command = self.build_preview_command(intent)
        command[1:3] = ["order", "place"]
        command.extend(["--execute", "--dangerously-skip-permissions", "--confirm", confirm_token])
        return command

    def preview_order(self, intent: OrderIntent) -> OrderPreview:
        return OrderPreview(
            broker="tossinvest",
            mode=ExecutionMode.preview,
            request=intent.model_dump(mode="json"),
            command=self.build_preview_command(intent),
            warnings=[
                "tossinvest-cli is an unofficial tool using internal web APIs.",
                "Use read-only and preview flows first; live trading should stay supervised.",
            ],
        )

    def submit_order(self, intent: OrderIntent, confirm_token: str) -> dict[str, Any]:
        command = self.build_execute_command(intent, confirm_token=confirm_token)
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "tossctl failed")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"raw": result.stdout.strip()}
