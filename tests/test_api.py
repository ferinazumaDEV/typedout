"""Tests for the public API surface listed in ``typedout.__all__``."""

from __future__ import annotations

import importlib.metadata

import pytest

import typedout
from typedout import (
    Completion,
    Message,
    Provider,
    ProviderError,
    RawUsage,
    TypedOut,
    TypedOutError,
)


def test_every_public_name_resolves():
    for name in typedout.__all__:
        assert getattr(typedout, name) is not None, name


def test_version_matches_installed_metadata():
    # The distribution is "typedout-py" while the import is "typedout": PyPI
    # refuses the bare name (it collides with the unrelated "typed-out" once
    # separators are normalised away). importlib.metadata looks things up by
    # DISTRIBUTION name, so this must not be "typedout" — see the README.
    #
    # The point of the test is unchanged: __version__ is a literal in
    # __init__.py and this is what catches it drifting from pyproject.toml.
    assert typedout.__version__ == importlib.metadata.version("typedout-py")


class _MinimalProvider(Provider):
    """Implements only ``complete``; ``stream`` must come from the base class."""

    model = "minimal-test-model"

    def complete(self, messages, *, schema=None, model=None, temperature=0.0, max_tokens=1024):
        return Completion(
            text='{"name": "Ada", "age": 36, "email": "ada@example.com"}',
            model=model or self.model,
            usage=RawUsage(input_tokens=1, output_tokens=1),
        )


def test_base_stream_fallback_yields_whole_completion_once():
    # This is the path AnthropicProvider/OpenAIProvider rely on today.
    provider = _MinimalProvider()
    messages = [Message("user", "hi")]
    chunks = list(provider.stream(messages))
    assert chunks == [provider.complete(messages).text]


class _BrokenProvider(Provider):
    model = "broken-test-model"

    def complete(self, messages, *, schema=None, model=None, temperature=0.0, max_tokens=1024):
        raise RuntimeError("boom")


def test_provider_error_is_a_typed_out_error(person_cls):
    assert issubclass(ProviderError, TypedOutError)
    llm = TypedOut(_BrokenProvider(), max_retries=0)
    with pytest.raises(TypedOutError) as exc:
        llm.extract(person_cls, "x")
    assert isinstance(exc.value, ProviderError)
    assert isinstance(exc.value.__cause__, RuntimeError)
