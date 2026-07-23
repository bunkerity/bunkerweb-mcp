"""Small ASGI test helpers that avoid a threaded test client."""

from __future__ import annotations

import json
from types import TracebackType
from urllib.parse import urlsplit

from asgiref.testing import ApplicationCommunicator
from starlette.types import ASGIApp
from starlette.websockets import WebSocketDisconnect


class WebSocketSession:
    """Drive one WebSocket connection directly through an ASGI app."""

    def __init__(self, app: ASGIApp, url: str) -> None:
        parsed = urlsplit(url)
        self._communicator = ApplicationCommunicator(
            app,
            {
                "type": "websocket",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "scheme": "ws",
                "path": parsed.path,
                "raw_path": parsed.path.encode(),
                "query_string": parsed.query.encode(),
                "headers": [(b"host", b"testserver")],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "subprotocols": [],
                "state": {},
                "extensions": {},
            },
        )

    async def __aenter__(self) -> WebSocketSession:
        await self._communicator.send_input({"type": "websocket.connect"})
        message = await self._communicator.receive_output()
        if message["type"] == "websocket.close":
            raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
        assert message["type"] == "websocket.accept"
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._communicator.future.done():
            await self._communicator.send_input({"type": "websocket.disconnect", "code": 1000})
        await self._communicator.wait()

    async def send_text(self, text: str) -> None:
        await self._communicator.send_input({"type": "websocket.receive", "text": text})

    async def send_json(self, data: object) -> None:
        await self.send_text(json.dumps(data))

    async def receive_text(self) -> str:
        message = await self._communicator.receive_output()
        if message["type"] == "websocket.close":
            raise WebSocketDisconnect(message.get("code", 1000), message.get("reason"))
        assert message["type"] == "websocket.send"
        return message["text"]

    async def receive_json(self) -> object:
        return json.loads(await self.receive_text())
