import asyncio
import json
import time
import websockets
from websocket_bridge import WebSocketMidiBroadcaster

def test_websocket_broadcast():
    print("Testing WebSocket Broadcaster...")
    broadcaster = WebSocketMidiBroadcaster(host="127.0.0.1", port=8765)
    broadcaster.start()
    time.sleep(0.5)

    received_messages = []

    async def client_listener():
        uri = "ws://127.0.0.1:8765"
        async with websockets.connect(uri) as ws:
            # 1. First message should be connected handshake
            msg = await ws.recv()
            received_messages.append(json.loads(msg))

            # 2. Receive note_on
            msg = await ws.recv()
            received_messages.append(json.loads(msg))

            # 3. Receive note_off
            msg = await ws.recv()
            received_messages.append(json.loads(msg))

            # 4. Receive sustain
            msg = await ws.recv()
            received_messages.append(json.loads(msg))

    async def run_test():
        task = asyncio.create_task(client_listener())
        await asyncio.sleep(0.2)
        
        # Broadcast test events
        broadcaster.note_on(60, 100)
        await asyncio.sleep(0.05)
        broadcaster.note_off(60)
        await asyncio.sleep(0.05)
        broadcaster.sustain(127)
        
        await task

    asyncio.run(run_test())
    broadcaster.stop()

    print(f"Total messages received: {len(received_messages)}")
    for i, m in enumerate(received_messages):
        print(f"  [{i}] {m}")

    assert len(received_messages) == 4
    assert received_messages[0]["type"] == "connected"
    assert received_messages[1]["type"] == "note_on" and received_messages[1]["note"] == 60 and received_messages[1]["velocity"] == 100
    assert received_messages[2]["type"] == "note_off" and received_messages[2]["note"] == 60
    assert received_messages[3]["type"] == "sustain" and received_messages[3]["value"] == 127 and received_messages[3]["is_down"] is True
    print("ALL WEBSOCKET BROADCAST TESTS PASSED!")

if __name__ == "__main__":
    test_websocket_broadcast()
