"""WebSocket server for the Odin-Discord plugin (protocol v1).

The plugin is the client: it connects to Odinus, authenticates with a
shared token and then exchanges one JSON message per text frame. The
full contract lives in Odin-Discord/PROTOCOLO.md.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import WSMsgType, web

LOGGER = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
DEFAULT_TIMEOUT = 10.0

EventListener = Callable[[str, dict[str, Any]], Awaitable[None]]


class BridgeUnavailable(Exception):
    """The Minecraft server is not connected or did not answer in time."""


class BridgeError(Exception):
    """The plugin answered a request with ``ok: false``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MinecraftBridge:
    """Accept the plugin connection, route events and send requests."""

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        path: str = "/minecraft",
    ) -> None:
        self.host = host
        self.port = port
        self.path = path
        self._token = token

        self._runner: web.AppRunner | None = None
        self._socket: web.WebSocketResponse | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._listeners: list[EventListener] = []

        self.hello: dict[str, Any] | None = None
        self.status: dict[str, Any] | None = None

    @property
    def connected(self) -> bool:
        """Return whether the plugin is currently connected."""
        return self._socket is not None and not self._socket.closed

    def add_listener(self, listener: EventListener) -> None:
        """Receive every event sent by the plugin.

        Besides the protocol events, the bridge emits ``disconnected``
        when the plugin connection is lost.

        Listeners run inside the read loop to keep events in order, so
        they must not await ``request()`` directly (its response could
        never be read); spawn a task for that instead.
        """
        self._listeners.append(listener)

    async def start(self) -> None:
        """Start listening for the plugin."""
        app = web.Application()
        app.router.add_get(self.path, self._handle_connection)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        LOGGER.info(
            "Minecraft bridge listening on ws://%s:%s%s",
            self.host,
            self.port,
            self.path,
        )

    async def stop(self) -> None:
        """Close the plugin connection and stop listening."""
        if self._socket is not None:
            await self._socket.close()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def request(
        self,
        request_type: str,
        data: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Send a request and wait for the plugin response data."""
        socket = self._socket

        if socket is None or socket.closed:
            raise BridgeUnavailable("not_connected")

        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future

        try:
            await socket.send_str(
                json.dumps(
                    {
                        "v": PROTOCOL_VERSION,
                        "type": request_type,
                        "id": request_id,
                        "data": data or {},
                    },
                    ensure_ascii=False,
                )
            )

            return await asyncio.wait_for(future, timeout)

        except (asyncio.TimeoutError, ConnectionError) as error:
            raise BridgeUnavailable("timeout") from error

        finally:
            self._pending.pop(request_id, None)

    async def _handle_connection(
        self,
        request: web.Request,
    ) -> web.StreamResponse:
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {self._token}"

        if not hmac.compare_digest(
            authorization.encode(),
            expected.encode(),
        ):
            LOGGER.warning(
                "Rejected Minecraft bridge connection from %s: invalid token.",
                request.remote,
            )
            return web.Response(status=401)

        socket = web.WebSocketResponse(
            max_msg_size=MAX_MESSAGE_BYTES * 4,
        )
        await socket.prepare(request)

        previous = self._socket
        self._socket = socket

        if previous is not None and not previous.closed:
            LOGGER.info("Replacing the previous Minecraft bridge connection.")
            await previous.close()

        LOGGER.info("Minecraft server connected from %s.", request.remote)

        try:
            async for message in socket:
                if message.type == WSMsgType.TEXT:
                    await self._handle_text(message.data)
                elif message.type == WSMsgType.ERROR:
                    LOGGER.warning(
                        "Minecraft bridge connection error: %s",
                        socket.exception(),
                    )

        finally:
            if self._socket is socket:
                self._socket = None
                self.status = None
                self._fail_pending()

                LOGGER.info("Minecraft server disconnected.")
                await self._dispatch("disconnected", {})

        return socket

    async def _handle_text(self, text: str) -> None:
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            return

        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return

        if (
            not isinstance(message, dict)
            or message.get("v") != PROTOCOL_VERSION
            or not isinstance(message.get("type"), str)
        ):
            return

        message_type = message["type"]
        data = message.get("data")

        if not isinstance(data, dict):
            data = {}

        if message_type == "response":
            future = self._pending.get(str(message.get("id")))

            if future is None or future.done():
                return

            if message.get("ok") is True:
                future.set_result(data)
            else:
                future.set_exception(
                    BridgeError(str(message.get("error") or "internal"))
                )
            return

        if message_type == "hello":
            self.hello = data
        elif message_type == "status":
            self.status = data

        await self._dispatch(message_type, data)

    async def _dispatch(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        for listener in self._listeners:
            try:
                await listener(event_type, data)
            except Exception:
                LOGGER.exception(
                    "Error handling Minecraft event %s",
                    event_type,
                )

    def _fail_pending(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(BridgeUnavailable("disconnected"))

        self._pending.clear()
