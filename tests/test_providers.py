"""Tests for the Anthropic/OpenAI provider payload mapping.

These use injected fake clients — no SDKs, no network, no API keys — to prove the
request/response translation is correct.
"""

from __future__ import annotations

from types import SimpleNamespace

from typedout.providers.anthropic import AnthropicProvider
from typedout.providers.base import Message
from typedout.providers.openai import OpenAIProvider


class FakeAnthropicMessages:
    """Mirrors the keyword list of ``anthropic`` SDK 1.x ``Messages.create``.

    Deliberately *no* ``**kwargs``: a keyword the real SDK does not accept (such
    as ``temperature``, removed in 1.x) must raise ``TypeError`` here as well, so
    the suite cannot mask that class of regression.
    """

    def __init__(self, recorder):
        self._recorder = recorder

    def create(
        self,
        *,
        max_tokens,
        messages,
        model,
        metadata=None,
        stop_sequences=None,
        stream=False,
        system=None,
        thinking=None,
        tool_choice=None,
        tools=None,
        extra_headers=None,
        extra_query=None,
        extra_body=None,
        timeout=None,
    ):
        self._recorder.update(
            {
                "max_tokens": max_tokens,
                "messages": messages,
                "model": model,
                "metadata": metadata,
                "stop_sequences": stop_sequences,
                "stream": stream,
                "system": system,
                "thinking": thinking,
                "tool_choice": tool_choice,
                "tools": tools,
                "extra_headers": extra_headers,
                "extra_query": extra_query,
                "extra_body": extra_body,
                "timeout": timeout,
            }
        )
        return SimpleNamespace(
            model="claude-3-5-sonnet-20241022",
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
            usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        )


class FakeAnthropicClient:
    def __init__(self):
        self.recorded = {}
        self.messages = FakeAnthropicMessages(self.recorded)


def test_anthropic_splits_system_and_maps_usage():
    client = FakeAnthropicClient()
    provider = AnthropicProvider(client=client)
    completion = provider.complete(
        [Message("system", "be precise"), Message("user", "extract this")]
    )
    # system goes to the top-level arg, not into messages
    assert client.recorded["system"] == "be precise"
    assert client.recorded["messages"] == [{"role": "user", "content": "extract this"}]
    # SDK 1.x has no `temperature` on messages.create; the provider must not send it.
    assert "temperature" not in client.recorded
    assert completion.text == '{"ok": true}'
    assert completion.usage.input_tokens == 11
    assert completion.usage.output_tokens == 7
    assert completion.model == "claude-3-5-sonnet-20241022"


class FakeCompletions:
    def __init__(self, recorder):
        self._recorder = recorder

    def create(self, **kwargs):
        self._recorder.update(kwargs)
        return SimpleNamespace(
            model="gpt-4o-mini",
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=13, completion_tokens=5),
        )


class FakeOpenAIClient:
    def __init__(self):
        self.recorded = {}
        self.chat = SimpleNamespace(completions=FakeCompletions(self.recorded))


def test_openai_maps_messages_and_usage():
    client = FakeOpenAIClient()
    provider = OpenAIProvider(client=client)
    completion = provider.complete(
        [Message("system", "be precise"), Message("user", "extract this")]
    )
    assert client.recorded["messages"] == [
        {"role": "system", "content": "be precise"},
        {"role": "user", "content": "extract this"},
    ]
    assert client.recorded["response_format"] == {"type": "json_object"}
    assert completion.text == '{"ok": true}'
    assert completion.usage.input_tokens == 13
    assert completion.usage.output_tokens == 5


def test_openai_json_mode_can_be_disabled():
    client = FakeOpenAIClient()
    provider = OpenAIProvider(client=client, json_mode=False)
    provider.complete([Message("user", "hi")])
    assert "response_format" not in client.recorded


def test_providers_are_lazy_importable():
    # Should be reachable from the package without the SDKs installed.
    import typedout

    assert typedout.AnthropicProvider is AnthropicProvider
    assert typedout.OpenAIProvider is OpenAIProvider
