from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.agents.llm_client import DEFAULT_MAX_TOKENS, AnthropicLLMClient, LLMResponseError


class _Widget(BaseModel):
    name: str
    count: int


class FakeAnthropicSDKClient:
    """Stands in for anthropic.Anthropic — records the call, returns a
    canned response shaped like the real SDK's Message object.
    """

    def __init__(self, response):
        self._response = response
        self.messages = SimpleNamespace(create=self._create)
        self.last_call = None

    def _create(self, **kwargs):
        self.last_call = kwargs
        return self._response


def _tool_use_response(tool_name: str, tool_input: dict):
    block = SimpleNamespace(type="tool_use", name=tool_name, input=tool_input)
    return SimpleNamespace(content=[block])


def test_generate_structured_parses_tool_use_block_into_output_model():
    sdk_client = FakeAnthropicSDKClient(
        _tool_use_response("_Widget", {"name": "gizmo", "count": 3})
    )
    client = AnthropicLLMClient(api_key="unused", client=sdk_client)

    result = client.generate_structured(
        system="be helpful", user_message="describe the widget", output_model=_Widget
    )

    assert result == _Widget(name="gizmo", count=3)


def test_generate_structured_forces_tool_choice_on_output_model():
    sdk_client = FakeAnthropicSDKClient(
        _tool_use_response("_Widget", {"name": "gizmo", "count": 3})
    )
    client = AnthropicLLMClient(api_key="unused", client=sdk_client)

    client.generate_structured(
        system="be helpful", user_message="describe the widget", output_model=_Widget
    )

    assert sdk_client.last_call["tool_choice"] == {"type": "tool", "name": "_Widget"}
    assert sdk_client.last_call["tools"][0]["name"] == "_Widget"
    assert sdk_client.last_call["tools"][0]["input_schema"] == _Widget.model_json_schema()


def test_generate_structured_raises_when_no_matching_tool_use_block():
    sdk_client = FakeAnthropicSDKClient(SimpleNamespace(content=[]))
    client = AnthropicLLMClient(api_key="unused", client=sdk_client)

    with pytest.raises(LLMResponseError):
        client.generate_structured(
            system="be helpful", user_message="describe the widget", output_model=_Widget
        )


def test_default_max_tokens_has_real_headroom_for_large_structured_outputs():
    # Regression guard: a live run hit stop_reason="max_tokens" on a
    # BullCase response at the old 4096 ceiling — it happened to still
    # produce valid JSON, but that was luck, not a guarantee (a truncated
    # tool_use JSON can just as easily leave required fields missing and
    # fail Pydantic validation). Judge's output is the largest of all —
    # it synthesizes both cases plus both rebuttals — so this needs to
    # stay comfortably above what a verbose multi-field structured
    # response like JudgeVerdict can reach.
    assert DEFAULT_MAX_TOKENS >= 8192


def test_generate_structured_sends_default_max_tokens():
    sdk_client = FakeAnthropicSDKClient(
        _tool_use_response("_Widget", {"name": "gizmo", "count": 3})
    )
    client = AnthropicLLMClient(api_key="unused", client=sdk_client)

    client.generate_structured(
        system="be helpful", user_message="describe the widget", output_model=_Widget
    )

    assert sdk_client.last_call["max_tokens"] == DEFAULT_MAX_TOKENS


def test_generate_structured_validates_tool_input_against_output_model():
    sdk_client = FakeAnthropicSDKClient(
        _tool_use_response("_Widget", {"name": "gizmo"})  # missing required "count"
    )
    client = AnthropicLLMClient(api_key="unused", client=sdk_client)

    with pytest.raises(Exception):  # pydantic.ValidationError
        client.generate_structured(
            system="be helpful", user_message="describe the widget", output_model=_Widget
        )
