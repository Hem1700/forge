"""WebSocket event streaming for live pentest monitoring."""
from __future__ import annotations
import asyncio
import json
import signal
from rich.console import Console
from forge_cli.display import format_event, console

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


async def _stream(ws_url: str, stop_event: asyncio.Event):
    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
            while not stop_event.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    if raw == "ping":
                        await ws.send("pong")
                        continue
                    event = json.loads(raw)
                    console.print(format_event(event))
                    if event.get("type") == "campaign_complete":
                        stop_event.set()
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
    except Exception as e:
        console.print(f"[dim]Stream disconnected: {e}[/dim]")


def stream_events(engagement_id: str, base_url: str = "http://localhost:8080"):
    if not HAS_WEBSOCKETS:
        console.print("[yellow]websockets not installed — cannot stream live events[/yellow]")
        return

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/{engagement_id}"

    stop_event = asyncio.Event()

    loop = asyncio.new_event_loop()

    def _sigint(_sig, _frame):
        stop_event.set()

    old = signal.signal(signal.SIGINT, _sigint)
    try:
        loop.run_until_complete(_stream(ws_url, stop_event))
    finally:
        signal.signal(signal.SIGINT, old)
        loop.close()
