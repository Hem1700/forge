"""WebSocket event streaming for live pentest monitoring."""
from __future__ import annotations
import asyncio
import json
import signal
import urllib.request
from forge_cli.display import format_event, console

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


_STALL_WARN = 30  # seconds of silence before printing a hint


def _approve_gate(base_url: str, api_key: str, engagement_id: str) -> None:
    url = f"{base_url}/api/v1/gates/{engagement_id}/decide"
    data = json.dumps({"approved": True, "notes": "auto-approved by CLI"}).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        console.print(f"  [yellow]Auto-approve failed: {e}[/yellow]")


async def _stream(
    ws_url: str,
    stop_event: asyncio.Event,
    engagement_id: str,
    base_url: str,
    api_key: str | None,
    auto_approve: bool,
):
    loop = asyncio.get_event_loop()
    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
            console.print("[dim green]✓ Stream connected[/dim green]")
            silent_for = 0.0
            stall_warned = False
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    silent_for = 0.0
                    stall_warned = False
                    if raw == "ping":
                        await ws.send("pong")
                        continue
                    event = json.loads(raw)
                    console.print(format_event(event))

                    etype = event.get("type")
                    if etype == "campaign_complete":
                        stop_event.set()
                    elif etype == "gate_triggered" and auto_approve and api_key:
                        gate = event.get("payload", {}).get("gate_status", "gate")
                        console.print(f"  [dim]Auto-approving {gate}…[/dim]")
                        await loop.run_in_executor(
                            None, _approve_gate, base_url, api_key, engagement_id
                        )

                except asyncio.TimeoutError:
                    silent_for += 1.0
                    if not stall_warned and silent_for >= _STALL_WARN:
                        console.print(
                            f"  [yellow]No events for {_STALL_WARN}s — is the worker running?[/yellow]\n"
                            f"  [dim]Check: forge status <id>  ·  Ctrl+C to detach[/dim]"
                        )
                        stall_warned = True
                    continue
                except Exception:
                    break
    except Exception as e:
        console.print(f"[dim]Stream disconnected: {e}[/dim]")


def stream_events(
    engagement_id: str,
    base_url: str = "http://localhost:8080",
    api_key: str | None = None,
    auto_approve: bool = True,
):
    if not HAS_WEBSOCKETS:
        console.print("[yellow]websockets not installed — cannot stream live events[/yellow]")
        return

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/{engagement_id}"
    if api_key:
        ws_url = f"{ws_url}?token={api_key}"

    stop_event = asyncio.Event()
    loop = asyncio.new_event_loop()

    def _sigint(_sig, _frame):
        stop_event.set()

    old = signal.signal(signal.SIGINT, _sigint)
    try:
        loop.run_until_complete(
            _stream(ws_url, stop_event, engagement_id, base_url, api_key, auto_approve)
        )
    finally:
        signal.signal(signal.SIGINT, old)
        loop.close()
