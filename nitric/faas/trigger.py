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
import typing

from nitric.proto.faas.v1.faas_pb2 import TriggerRequest

from nitric.faas.response import Response, TopicResponseContext, HttpResponseContext, ResponseContext


class HttpTriggerContext(object):
    """Represents Trigger metadata from a HTTP subscription"""

    def __init__(
        self,
        method: str,
        headers: typing.Dict[str, str],
        path_params: typing.Dict[str, str],
        query_params: typing.Dict[str, str],
    ):
        self.method = method
        self.headers = headers
        self.path_params = path_params
        self.query_params = query_params


class TopicTriggerContext(object):
    """Represents Trigger metadata from a topic subscription"""

    def __init__(self, topic: str):
        self.topic = topic


class TriggerContext(object):
    """Represents the contextual metadata for a Nitric function request."""

    def __init__(self, context: typing.Union[TopicTriggerContext, HttpTriggerContext]):
        """Construct a Nitric Trigger Context."""
        self.context = context

    def is_http(self) -> bool:
        return isinstance(self.context, HttpTriggerContext)

    def as_http(self) -> typing.Union[HttpTriggerContext, None]:
        if not self.is_http():
            return None

        return self.context

    def is_topic(self) -> bool:
        return isinstance(self.context, TriggerContext)

    def as_topic(self) -> typing.Union[TopicTriggerContext, None]:
        if not self.is_topic():
            return None

        return self.context

    @staticmethod
    def from_trigger_request(trigger_request: TriggerRequest):
        if trigger_request.http is not None:
            return TriggerContext(
                context=HttpTriggerContext(
                    headers=trigger_request.http.headers,
                    method=trigger_request.http.method,
                    query_params=trigger_request.http.query_params,
                    path_params=trigger_request.http.path_params,
                )
            )
        elif trigger_request.topic is not None:
            return TriggerContext(context=TopicTriggerContext(topic=trigger_request.topic.topic))
        else:
            # We have an error
            # should probably raise an exception
            return None


def _clean_header(header_name: str):
    """Convert a Nitric HTTP request header name into the equivalent Context property name."""
    return header_name.lower().replace("x-nitric-", "").replace("-", "_")


class Trigger(object):
    """
    Represents a standard Nitric function request.

    These requests are normalized from their original stack-specific structures.
    """

    def __init__(self, context: TriggerContext, data: bytes):
        """Construct a Nitric Function Request."""
        self.context = context
        self.data = data

    def get_body(self) -> bytes:
        """Return the bytes of the body of the request."""
        return self.data

    def get_object(self) -> dict:
        """
        Assume the payload is JSON and return the content deserialized into a dictionary.

        :raises JSONDecodeError: raised when the request payload (body) is not valid JSON.

        :return: the deserialized JSON request body as a dictionary
        """
        import json

        return json.loads(self.data)

    def default_response(self) -> Response:
        """
        Convenience method to construct a relevant default response
        The returned response can be interrogated with its context to determine the appropriate
        response context e.g. response.context.is_http() or response.context.is_topic()
        """
        response_ctx = None

        if self.context.is_http():
            response_ctx = ResponseContext(context=HttpResponseContext())
        elif self.context.is_topic():
            response_ctx = ResponseContext(context=TopicResponseContext())

        return Response(data=None, context=response_ctx)

    @staticmethod
    def from_trigger_request(trigger_request: TriggerRequest):
        context = TriggerContext.from_trigger_request(trigger_request)

        return Trigger(context=context, data=trigger_request.data)
