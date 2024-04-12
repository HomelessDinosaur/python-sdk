#
# Copyright (c) 2021 Nitric Technologies Pty Ltd.
#
# This file is part of Nitric Python 3 SDK.
# See https://github.com/nitrictech/python-sdk for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import annotations

import functools
import inspect
import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Protocol, TypeVar, Union

from opentelemetry import propagate

from nitric.proto.schedules.v1 import ServerMessage as ScheduleServerMessage
from nitric.proto.topics.v1 import ClientMessage as TopicClientMessage
from nitric.proto.topics.v1 import MessageResponse as TopicResponse
from nitric.proto.topics.v1 import ServerMessage as TopicServerMessage

Record = Dict[str, Union[str, List[str]]]
PROPAGATOR = propagate.get_global_textmap()


class HttpMethod(Enum):
    """Valid query expression operators."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"

    def __str__(self):
        return str(self.value)


class TriggerContext(Protocol):
    """Represents an abstract request/response context for any trigger."""

    @staticmethod
    def _from_request(server_message) -> TriggerContext:
        """Convert a server message request into this trigger context."""
        pass

    def to_response(self):
        """Convert this trigger context into a server message response."""
        pass


# ====== HTTP ======


class HttpRequest:
    """Represents a translated Http Request forwarded from the Nitric Membrane."""

    def __init__(
        self,
        data: bytes,
        method: str,
        path: str,
        params: Dict[str, str],
        query: Record,
        headers: Record,
    ):
        """Construct a new HttpRequest."""
        self.data = data
        self.method = method
        self.path = path
        self.params = params
        self.query = query
        self.headers = headers

    @property
    def json(self) -> Optional[Any]:
        """Get the body of the request as JSON, returns None if request body is not JSON."""
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            return None
        except TypeError:
            return None

    @property
    def body(self):
        """Get the body of the request as text."""
        return self.data.decode("utf-8")


class HttpResponse:
    """Represents an HTTP Response to be generated by the Nitric Membrane in response to an HTTP Request Trigger."""

    def __init__(self, status: int = 200, headers: Optional[Record] = None, body: Optional[bytes] = None):
        """Construct a new HttpResponse."""
        self.status = status
        self.headers = headers if headers else {}
        self._body = body if body else bytes()

    @property
    def body(self):
        """Return the HTTP response body."""
        return self._body

    @body.setter
    def body(self, value: Union[str, bytes, Any]):
        if isinstance(value, str):
            self._body = value.encode("utf-8")
        elif isinstance(value, bytes):
            self._body = value
        else:
            self._body = json.dumps(value).encode("utf-8")
            self.headers["Content-Type"] = ["application/json"]


class HttpContext:
    """Represents the full request/response context for an Http based trigger."""

    def __init__(self, request: HttpRequest, response: Optional[HttpResponse] = None):
        """Construct a new HttpContext."""
        self.req = request
        self.res = response if response else HttpResponse()

    @staticmethod
    def _ensure_value_is_list(value: Union[str, List[str]]) -> List[str]:
        return list(value) if isinstance(value, list) else [value]


class MessageRequest:
    """Represents a translated Event, from a Subscribed Topic, forwarded from the Nitric Membrane."""

    data: dict[str, Any]
    topic: str

    def __init__(self, data: dict[str, Any], topic: str):
        """Construct a new EventRequest."""
        self.data = data
        self.topic = topic


class MessageResponse:
    """Represents the response to a trigger from an Event as a result of a Topic subscription."""

    def __init__(self, success: bool = True):
        """Construct a new EventResponse."""
        self.success = success


class MessageContext:
    """Represents the full request/response context for an Event based trigger."""

    def __init__(self, request: MessageRequest, response: Optional[MessageResponse] = None):
        """Construct a new EventContext."""
        self.req = request
        self.res = response if response else MessageResponse()

    @staticmethod
    def _from_request(msg: TopicServerMessage) -> MessageContext:
        """Construct a new EventContext from a Topic trigger from the Nitric Membrane."""
        return MessageContext(
            request=MessageRequest(
                data=msg.message_request.message.struct_payload.to_dict(),
                topic=msg.message_request.topic_name,
            )
        )

    def to_response(self) -> TopicClientMessage:
        """Construct a EventContext for the Nitric Membrane from this context object."""
        return TopicClientMessage(message_response=TopicResponse(success=self.res.success))


# == WEBSOCKET ==


class WebsocketRequest:
    """Represents an incoming websocket event."""

    def __init__(self, connection_id: str):
        """Construct a new WebsocketRequest."""
        self.connection_id = connection_id


class WebsocketConnectionRequest(WebsocketRequest):
    """Represents an incoming websocket connection."""

    query: Dict[str, str | List[str]]

    def __init__(self, connection_id: str, query: Dict[str, str | List[str]]):
        """Construct a new WebsocketConnectionRequest."""
        super().__init__(connection_id=connection_id)
        self.query = query


class WebsocketMessageRequest(WebsocketRequest):
    """Represents an incoming websocket message."""

    data: bytes

    def __init__(self, connection_id: str, data: bytes):
        """Construct a new WebsocketMessageRequest."""
        super().__init__(connection_id=connection_id)
        self.data = data


class WebsocketResponse:
    """Represents a response to a websocket event."""

    def __init__(self):
        """Construct a new WebsocketResponse."""


class WebsocketConnectionResponse(WebsocketResponse):
    """Represents a response to a websocket connection event."""

    reject: bool

    def __init__(self, reject: bool = False):
        """Construct a new WebsocketConnectionResponse."""
        self.reject = reject


AnyWebsocketRequest = Union[WebsocketRequest, WebsocketConnectionRequest, WebsocketMessageRequest]
AnyWebsocketResponse = Union[WebsocketResponse, WebsocketConnectionResponse]


class WebsocketContext:
    """Represents the full request/response context for a Websocket based trigger."""

    def __init__(self, request: AnyWebsocketRequest, response: Optional[AnyWebsocketResponse] = None):
        """Construct a new WebsocketContext."""
        self.req = request
        if response:
            self.res = response
        elif isinstance(request, WebsocketConnectionRequest):
            self.res = WebsocketConnectionResponse()
        else:
            self.res = WebsocketResponse()


# == Schedules ==


class IntervalRequest:
    """Represents a translated Event, from a Schedule, forwarded from the Nitric Membrane."""

    def __init__(self, schedule_name: str):
        """Construct a new IntervalRequest."""
        self.schedule_name = schedule_name


class IntervalResponse:
    """Represents the response to a trigger from an Interval as a result of a Schedule."""

    _request_id: str

    def __init__(self, request_id: str):
        """Construct a new IntervalResponse."""
        self._request_id = request_id


class IntervalContext:
    """Represents the full request/response context for a scheduled trigger."""

    def __init__(self, msg: ScheduleServerMessage):
        """Construct a new EventContext."""
        self.req = IntervalRequest(schedule_name=msg.interval_request.schedule_name)
        self.res = IntervalResponse(msg.id)


C = TypeVar("C")


class Middleware(Protocol, Generic[C]):
    """A middleware function."""

    async def __call__(self, ctx: C, nxt: Optional[Middleware[C]] = None) -> C:
        """Process trigger context."""
        ...


class Handler(Protocol, Generic[C]):
    """A handler function."""

    async def __call__(self, ctx: C) -> C | None:
        """Process trigger context."""
        ...


HttpMiddleware = Middleware[HttpContext]
EventMiddleware = Middleware[MessageContext]
IntervalMiddleware = Middleware[IntervalContext]
WebsocketMiddleware = Middleware[WebsocketContext]

HttpHandler = Handler[HttpContext]
EventHandler = Handler[MessageContext]
IntervalHandler = Handler[IntervalContext]
WebsocketHandler = Handler[WebsocketContext]


def _convert_to_middleware(handler: Handler[C] | Middleware[C]) -> Middleware[C]:
    """Convert a handler to a middleware, if it's already a middleware it's returned unchanged."""
    if not _is_handler(handler):
        # it's not a middleware, don't convert it.
        return handler  # type: ignore

    async def middleware(ctx: C, nxt: Middleware[C]) -> C:
        context = await handler(ctx)  # type: ignore
        return await nxt(context) if nxt else context  # type: ignore

    return middleware  # type: ignore


def _is_handler(unknown: Middleware[C] | Handler[C]) -> bool:
    """Return True if the provided function is a handler (1 positional arg)."""
    signature = inspect.signature(unknown)
    params = signature.parameters
    positional = [name for name, param in params.items() if param.default == inspect.Parameter.empty]
    return len(positional) == 1


def compose_middleware(*middlewares: Middleware[C] | Handler[C]) -> Middleware[C]:
    """
    Compose multiple middleware functions into a single middleware function.

    The resulting middleware will effectively be a chain of the provided middleware,
    where each calls the next in the chain when they're successful.
    """
    middlewares = [_convert_to_middleware(middleware) for middleware in middlewares]  # type: ignore

    async def composed(ctx: C, nxt: Optional[Middleware[C]] = None) -> C:
        last_middleware = nxt

        def reduce_chain(acc_next: Middleware[C], cur: Middleware[C]) -> Middleware[C]:
            async def chained_middleware(ctx: C, nxt: Optional[Middleware[C]] = None) -> C:
                result = (await nxt(ctx)) if nxt is not None else ctx  # type: ignore
                # type ignored because mypy appears to misidentify the correct return type
                output_context = await cur(result, acc_next)  # type: ignore
                if not output_context:
                    return result  # type: ignore
                return output_context  # type: ignore

            return chained_middleware

        middleware_chain = functools.reduce(reduce_chain, reversed(middlewares), last_middleware)  # type: ignore
        # type ignored because mypy appears to misidentify the correct return type
        return await middleware_chain(ctx)  # type: ignore

    return composed


class FunctionServer(ABC):
    """Represents a worker that should be started at runtime."""

    @abstractmethod
    async def start(self) -> None:
        """Start the worker."""
