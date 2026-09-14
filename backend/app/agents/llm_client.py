"""Thin wrapper over Anthropic's Messages API that forces structured,
Pydantic-validated output via tool-calling — agent responses are never
parsed from prose (CLAUDE.md: "All agent inputs/outputs are Pydantic
models... No agent communicates in free-form prose").
"""

from typing import TypeVar

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-sonnet-5"
# A live run hit stop_reason="max_tokens" on a BullCase response at the
# old 4096 ceiling. Judge's output (synthesizes both cases + both
# rebuttals) is the largest structured response in the pipeline, so this
# needs real headroom above it. Raising this costs nothing unless a
# response actually needs the extra room — Anthropic bills only for
# tokens generated, not the ceiling.
DEFAULT_MAX_TOKENS = 8192

T = TypeVar("T", bound=BaseModel)


class LLMResponseError(RuntimeError):
    """The model's response didn't contain the expected structured tool call."""


class AnthropicLLMClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        client: anthropic.Anthropic | None = None,
    ):
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_structured(self, *, system: str, user_message: str, output_model: type[T]) -> T:
        tool_name = output_model.__name__
        response = self._client.messages.create(
            model=self._model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Return a structured {tool_name}.",
                    "input_schema": output_model.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return output_model.model_validate(block.input)
        raise LLMResponseError(f"Anthropic response had no {tool_name!r} tool_use block")
