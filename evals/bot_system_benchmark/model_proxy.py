"""Budgeted local transport to the user-authorized Nous model, with safe receipts."""

from __future__ import annotations

from contextlib import AbstractContextManager
from decimal import Decimal
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

import httpx

MODEL = "deepseek/deepseek-v4.1-flash"
MAX_OUTPUT = 2048
MAX_INPUT_BYTES = 160_000


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def stream_response(payload: dict) -> bytes:
    choice = payload["choices"][0]
    message = json.loads(json.dumps(choice["message"]))
    for index, call in enumerate(message.get("tool_calls") or []):
        call["index"] = index
    common = {
        "id": payload.get("id", "portal-eval"),
        "object": "chat.completion.chunk",
        "created": payload.get("created", 0),
        "model": payload.get("model", MODEL),
    }
    chunks = [
        {**common, "choices": [{"index": 0, "delta": message, "finish_reason": None}]},
        {
            **common,
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason")}
            ],
            "usage": payload.get("usage"),
        },
    ]
    return (
        "".join("data: " + json.dumps(row) + "\n\n" for row in chunks)
        + "data: [DONE]\n\n"
    ).encode()


class PortalProxy(AbstractContextManager):
    def __init__(
        self,
        credentials: dict,
        pricing: dict,
        ledger_path: Path,
        *,
        allow_local=False,
        reservation_ceiling="4.50",
        request_limit=400,
    ):
        base = credentials["base_url"].rstrip("/")
        parsed = urlparse(base)
        allowed = (
            parsed.scheme == "https"
            and parsed.hostname == "inference-api.nousresearch.com"
        )
        if not allowed and not (allow_local and parsed.hostname == "127.0.0.1"):
            raise ValueError("Only the authorized Nous inference host is accepted")
        self.url = base + "/chat/completions"
        self.key = credentials["api_key"]
        self.pricing = pricing
        original = pricing.get("original") or {}
        self.input_rate = max(
            Decimal(pricing["prompt"]), Decimal(original.get("prompt", "0"))
        )
        self.output_rate = max(
            Decimal(pricing["completion"]), Decimal(original.get("completion", "0"))
        )
        self.ledger_path = ledger_path
        self.reservation_ceiling = Decimal(reservation_ceiling)
        self.request_limit = request_limit
        if (
            not 0 < self.reservation_ceiling <= Decimal("5.00")
            or not 0 < request_limit <= 500
        ):
            raise ValueError(
                "Evaluation guard exceeds the user's $5 authority or request limit"
            )
        self.lock = threading.Lock()
        self.label = "unassigned"
        self.ledger = {
            "model": MODEL,
            "authorized_cap_usd": "5.00",
            "reservation_ceiling_usd": "4.50",
            "reservation_safety_factor": 2,
            "pricing": pricing,
            "reservations_usd": "0",
            "note": "Reservations use UTF-8 request bytes plus 8192 overhead tokens and the output cap, at doubled current/original catalog rates. No reservation is refunded. This is a conservative estimate, not a provider invoice.",
            "requests": [],
        }
        if ledger_path.exists():
            self.ledger = json.loads(ledger_path.read_text())
            if (
                self.ledger.get("model") != MODEL
                or self.ledger.get("authorized_cap_usd") != "5.00"
            ):
                raise ValueError("Existing budget ledger has incompatible authority")
        if (
            self.ledger.get("reservation_ceiling_usd") != str(self.reservation_ceiling)
            or self.ledger.get("request_limit", 400) != self.request_limit
        ):
            self.ledger.setdefault("guard_history", []).append(
                {
                    "previous_ceiling_usd": self.ledger.get("reservation_ceiling_usd"),
                    "ceiling_usd": str(self.reservation_ceiling),
                    "request_limit": self.request_limit,
                    "note": "Predeclared protocol extension under the same $5 authority; no reservations refunded.",
                }
            )
        self.ledger.update(
            reservation_ceiling_usd=str(self.reservation_ceiling),
            request_limit=self.request_limit,
        )
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                owner.handle(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.save()

    def save(self):
        self.ledger_path.write_text(json.dumps(self.ledger, indent=2) + "\n")

    def reserve(self, body: dict, size: int) -> dict | None:
        amount = 2 * ((size + 8192) * self.input_rate + MAX_OUTPUT * self.output_rate)
        with self.lock:
            total = Decimal(self.ledger["reservations_usd"])
            launch_count = sum(
                row["launch"] == self.label for row in self.ledger["requests"]
            )
            if (
                total + amount > self.reservation_ceiling
                or len(self.ledger["requests"]) >= self.request_limit
                or launch_count >= 16
            ):
                return None
            row = {
                "launch": self.label,
                "status": "admitted",
                "reservation_usd": str(amount),
                "request_sha256": digest(body),
                "input_bytes": size,
                "message_sha256": [
                    digest(message) for message in body.get("messages", [])
                ],
                "roles": [message.get("role") for message in body.get("messages", [])],
                "tools_sha256": digest(body.get("tools")),
                "tool_names": [
                    item.get("function", {}).get("name")
                    for item in body.get("tools", [])
                ],
                "tool_calls": [
                    message["tool_calls"]
                    for message in body.get("messages", [])
                    if message.get("tool_calls")
                ],
                "tool_results": [
                    message
                    for message in body.get("messages", [])
                    if message.get("role") == "tool"
                ],
            }
            self.ledger["requests"].append(row)
            self.ledger["reservations_usd"] = str(total + amount)
            self.save()
            return row

    @staticmethod
    def respond(handler, status: int, payload: bytes, content_type="application/json"):
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def handle(self, handler):
        size = int(handler.headers.get("Content-Length", "0"))
        if handler.path != "/v1/chat/completions" or not 0 < size <= MAX_INPUT_BYTES:
            self.respond(
                handler,
                400,
                b'{"error":{"message":"Evaluation request boundary exceeded"}}',
            )
            return
        body = json.loads(handler.rfile.read(size))
        row = self.reserve(body, size)
        if row is None:
            self.respond(
                handler,
                429,
                b'{"error":{"message":"Evaluation spending or request budget exhausted"}}',
            )
            return
        streaming = body.pop("stream", False)
        for name in ("stream_options", "max_completion_tokens", "reasoning_effort"):
            body.pop(name, None)
        body.update(
            model=MODEL,
            max_tokens=MAX_OUTPUT,
            reasoning={"enabled": False},
            temperature=0,
            stream=False,
        )
        row["effective_request_sha256"] = digest(body)
        try:
            with httpx.Client(timeout=70, follow_redirects=False) as client:
                response = client.post(
                    self.url, headers={"Authorization": "Bearer " + self.key}, json=body
                )
            payload = response.json()
            row.update(
                status="completed", http_status=response.status_code, response=payload
            )
            if response.is_success and streaming:
                self.respond(
                    handler, 200, stream_response(payload), "text/event-stream"
                )
            else:
                self.respond(
                    handler, response.status_code, json.dumps(payload).encode()
                )
        except (httpx.HTTPError, ValueError, OSError, KeyError) as exc:
            row.update(status="transport_error", error=type(exc).__name__)
            self.respond(
                handler,
                502,
                b'{"error":{"message":"Evaluation upstream transport failed"}}',
            )
        finally:
            with self.lock:
                self.save()

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.key = ""
