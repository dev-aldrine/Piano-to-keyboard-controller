import asyncio
import json
import threading
import time
from typing import Set, Optional, Callable
import websockets

class WebSocketMidiBroadcaster:
    """
    Ultra low-latency local WebSocket server (ws://localhost:8765)
    Broadcasting real-time MIDI events (Note On, Note Off, Sustain/CC)
    to Web clients like PianoWeb.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.on_log_cb: Optional[Callable[[str], None]] = None
        self.on_client_count_change_cb: Optional[Callable[[int], None]] = None

    def _log(self, msg: str):
        if self.on_log_cb:
            self.on_log_cb(msg)
        else:
            print(f"[WebSocketBridge] {msg}")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_event_loop, daemon=True, name="WebSocketBridgeThread")
        self.thread.start()

    def _run_event_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_server())
            self.loop.run_forever()
        except Exception as e:
            self._log(f"WebSocket server error: {e}")
        finally:
            self.loop.close()

    async def _start_server(self):
        try:
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=10,
                ping_timeout=10
            )
            self._log(f"WebSocket Bridge active on ws://{self.host}:{self.port} (Broadcasting to PianoWeb)")
        except Exception as e:
            self._log(f"Failed to bind WebSocket server to {self.host}:{self.port}: {e}")

    async def _handle_client(self, websocket):
        self.clients.add(websocket)
        count = len(self.clients)
        self._log(f"Web Client Connected (Total: {count} active)")
        if self.on_client_count_change_cb:
            self.on_client_count_change_cb(count)
        try:
            # Send greeting/handshake
            await websocket.send(json.dumps({
                "type": "connected",
                "message": "Connected to Python MIDI Bridge",
                "timestamp": time.time()
            }))
            # Keep listening for any messages / client close
            async for message in websocket:
                pass
        except Exception:
            pass
        finally:
            self.clients.discard(websocket)
            count = len(self.clients)
            self._log(f"Web Client Disconnected (Total: {count} active)")
            if self.on_client_count_change_cb:
                self.on_client_count_change_cb(count)

    def broadcast(self, payload: dict):
        """Thread-safe non-blocking broadcast to all active WebSocket clients."""
        if not self.is_running or not self.loop or not self.clients:
            return
        try:
            message = json.dumps(payload)
            asyncio.run_coroutine_threadsafe(self._async_broadcast(message), self.loop)
        except Exception:
            pass

    async def _async_broadcast(self, message: str):
        if not self.clients:
            return
        # Broadcast concurrently to all connected clients
        tasks = [client.send(message) for client in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)

    def note_on(self, note: int, velocity: int):
        self.broadcast({
            "type": "note_on",
            "note": int(note),
            "velocity": int(velocity)
        })

    def note_off(self, note: int):
        self.broadcast({
            "type": "note_off",
            "note": int(note)
        })

    def sustain(self, value: int):
        self.broadcast({
            "type": "sustain",
            "value": int(value),
            "is_down": bool(value >= 64)
        })

    def stop(self):
        self.is_running = False
        if self.loop and self.server:
            try:
                self.server.close()
                self.loop.call_soon_threadsafe(self.loop.stop)
            except Exception:
                pass
