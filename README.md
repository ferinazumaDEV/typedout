# typedout

[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![tests](https://img.shields.io/badge/tests-100%20passing-brightgreen.svg)](tests/)

**Reliable structured output from OpenAI and Anthropic, with a provider interface for others.** Define a schema, get back a validated object — with tolerant JSON repair, error-aware retries, and an offline mock provider. No API key needed to try it.

```python
from pydantic import BaseModel
from typedout import TypedOut, MockProvider

class Person(BaseModel):
    name: str
    age: int
    email: str

llm = TypedOut(MockProvider(script=["invalid", "valid"]))
person = llm.extract(Person, "Ada Lovelace, 36, ada@example.com")

print(person)            # name='Ada Lovelace' age=36 email='ada@example.com'
print(llm.last_usage)    # 2 req · 352 in + 19 out = 371 tok · $0.000000
```

---

## Why

Getting *valid, typed* data out of an LLM is deceptively hard. Models wrap JSON in
```` ```json ```` fences, add a "Sure, here you go" preamble, emit Python's
`True`/`None`, leave trailing commas, use single quotes, or simply get cut off
mid-object at the token limit. `typedout` handles all of that behind one small API:

- **Tolerant JSON repair** — a single-pass, string-aware scanner turns *almost*-JSON into strict JSON (no `eval`, no network).
- **Schema validation** — pydantic models *or* raw JSON Schema dicts.
- **Error-aware retries** — when validation fails, the concrete errors are fed back to the model and it tries again.
- **Provider-agnostic** — Anthropic, OpenAI, or your own; a deterministic **`MockProvider`** is included so tests and demos run fully offline.
- **Extras** — partial-object **streaming**, **token/cost tracking**, and an **`@extract` decorator** that turns any function into a typed extractor.

## Install

```bash
pip install typedout-py                # core (pydantic only)
pip install "typedout-py[anthropic]"   # + Anthropic SDK
pip install "typedout-py[openai]"      # + OpenAI SDK
```

**Install `typedout-py`, import `typedout`.** The distribution name carries a `-py`
suffix; the package you import does not:

```python
from typedout import TypedOut
```

Requires Python 3.10+. The only hard dependency is `pydantic>=2`.

> **Renamed from `structllm` on 4 Sep 2026.** The distribution name `structllm` is
> held on PyPI by a different project doing the same thing — *"Universal Python
> library for Structured Outputs with any LLM provider"* — so this package could
> never have been published under it, and anyone searching for that name would have
> found the other library. The GitHub URL of the old name still redirects here.
>
> **And why the `-py` suffix.** PyPI also refuses the bare name `typedout`: it
> normalises away `-`, `_` and `.` before comparing, so `typedout` collides with an
> unrelated project called `typed-out`. Renaming the library a third time would have
> cost more than it is worth, so the distribution is `typedout-py` and the import
> stays `typedout` — the same split as `beautifulsoup4`/`bs4` or `pillow`/`PIL`.

## Usage

### 1. Extract a typed object

```python
from pydantic import BaseModel, Field
from typedout import TypedOut
from typedout import AnthropicProvider          # or OpenAIProvider, or your own

class Invoice(BaseModel):
    number: str
    total: float = Field(ge=0)
    currency: str

llm = TypedOut(AnthropicProvider())  # defaults to claude-opus-5
invoice = llm.extract(Invoice, "Invoice INV-2043, total 1,299.00 EUR, due in 30 days")
# -> Invoice(number='INV-2043', total=1299.0, currency='EUR')
```

The default is **`claude-opus-5`** — the strongest model, chosen because the
retry loop feeds validation errors back to the model, and a model that gets it
right first time is often cheaper per *successful extraction* than a cheaper one
that needs three attempts. It is not the cheapest per token: at the time of
writing it is $5 / $25 per million input / output tokens against $2 / $10 for
`claude-sonnet-5`. Pass `model=` to choose another, and read `llm.last_usage`
for what a call actually cost.


The schema is injected into the prompt automatically. If the model's reply doesn't
parse or doesn't validate, `typedout` repairs it, and — if it still fails —
re-prompts with the exact errors (up to `max_retries`, default 2).

### 2. The repair engine, standalone

`repair_json` is useful on its own. These are **real outputs** from the library:

```python
from typedout import repair_json

repair_json("```json\n{'name': 'Ada', 'age': 36,}\n```")
# -> {"name":"Ada","age":36}

repair_json('{"name": "Ada", "age": 36, "email": "ada@exampl')     # truncated
# -> {"name":"Ada","age":36,"email":"ada@exampl"}

repair_json("{name: 'Ada', active: True, mgr: None}")              # JS/Python-isms
# -> {"name":"Ada","active":true,"mgr":null}

repair_json('Sure! Here you go:\n{"score": 9.5}\nHope that helps!') # prose around it
# -> {"score":9.5}
```

| Fixes | Example in → out |
| --- | --- |
| Markdown fences | ```` ```json {...} ``` ```` → `{...}` |
| Surrounding prose | `Here you go: {...} thanks!` → `{...}` |
| Trailing commas | `[1, 2, 3,]` → `[1, 2, 3]` |
| Single quotes | `{'a': 'b'}` → `{"a": "b"}` |
| Unquoted keys | `{a: 1}` → `{"a": 1}` |
| Python literals | `True / False / None` → `true / false / null` |
| `//` and `/* */` comments | stripped |
| Truncated output | `{"a": [1, 2` → `{"a": [1, 2]}` |

### 3. `@extract` — a typed extractor in three lines

```python
from typedout import extract, MockProvider

@extract(Person, provider=MockProvider(script=["valid"]))
def parse_person(text: str) -> Person:
    return f"Extract the person described here:\n{text}"

parse_person("Ada Lovelace, 36, ada@example.com")   # -> Person(...)
```

The function just builds the prompt; the decorator runs extraction and returns the
validated object of the declared type.

### 4. Stream a partial object as it fills in

```python
llm = TypedOut(MockProvider(script=["valid"], chunk_size=8))
for partial in llm.stream(Person, "Ada Lovelace, 36, ada@example.com"):
    print(partial)
print(repr(llm.last_result))   # fully validated Person
```

Real output — the object materialises field by field, even from a half-received stream:

```
{}
{'name': 'Ada'}
{'name': 'Ada Lovelac'}
{'name': 'Ada Lovelace'}
{'name': 'Ada Lovelace', 'age': 36}
{'name': 'Ada Lovelace', 'age': 36, 'email': 'ada'}
{'name': 'Ada Lovelace', 'age': 36, 'email': 'ada@example'}
{'name': 'Ada Lovelace', 'age': 36, 'email': 'ada@example.com'}
Person(name='Ada Lovelace', age=36, email='ada@example.com')
```

> `AnthropicProvider` and `OpenAIProvider` do not yet implement token streaming; with them `stream()` yields a single snapshot containing the full object. Override `Provider.stream()` in your own provider to get progressive snapshots.

### 5. Track tokens and cost

```python
llm = TypedOut(OpenAIProvider(model="gpt-4o-mini"), model="gpt-4o-mini")
llm.extract(Invoice, "...")
print(llm.last_usage)     # this call, incl. retries
print(llm.total_usage)    # running total for the session
# 1 req · 166 in + 15 out = 181 tok · $0.000034
```

Prices are configurable (`register_price(...)`) and default to illustrative values —
nothing here bills you or calls the network.

### 6. Raw JSON Schema, no pydantic

Pass a plain dict and get a validated dict back, checked by the built-in lite
validator (`type`, `required`, `enum`, bounds, `anyOf`, `$ref`, …):

```python
schema = {
    "type": "object",
    "properties": {"id": {"type": "integer"}, "priority": {"enum": ["low", "high"]}},
    "required": ["id"],
}
llm.extract(schema, "ticket 7, high priority")   # -> {"id": 7, "priority": "high"}
```

## How it works

```
prompt ─▶ Provider.complete ─▶ repair(text) ─▶ validate(schema) ─▶ typed object
                  ▲                                     │
                  └──────── re-prompt with errors ◀─────┘  (up to max_retries)
```

1. **Prompt** — the JSON Schema is embedded in a system prompt asking for a single JSON object.
2. **Repair** — `repair.py` scans the reply character by character. Strings are re-encoded through `json.dumps` (so their contents are never corrupted); unbalanced braces are closed; it stops at the first complete top-level value, ignoring trailing prose.
3. **Validate** — pydantic (typed instance) or `jsonschema_lite` (dict).
4. **Retry** — on failure the assistant's bad answer plus a precise correction ("field `age`: input should be a valid integer") are appended, and the model tries again.

Every layer is independent: use `repair_json` alone, swap the provider, or drive the
whole thing offline with `MockProvider` — which can synthesise schema-valid answers
(it honours `type`, `enum`, numeric bounds, string `minLength`/`maxLength` and the
common `format`s; a `pattern` is not synthesised) or deliberately produce **fenced**,
**loose**, **truncated**, or **invalid** replies to exercise the repair and retry paths.

## Testing

```bash
pip install -e ".[dev]"
pytest                    # 100 tests, fully offline
python examples/quickstart.py
```

The suite covers the repair scanner (fences, comments, truncation, unicode, nested
mess), the JSON Schema validator, the retry loop, streaming, cost math, and the
Anthropic/OpenAI payload mapping (via injected fake clients — no SDKs, no keys).

## Part of the ferinazumaDEV ecosystem

`typedout` is one of a set of small, focused tools by ferinazumaDEV for building reliably with LLMs — here, turning free-form model output into schema-validated, machine-readable data you can trust. Related projects:

- [The GEO Handbook](https://github.com/ferinazumaDEV/generative-engine-optimization-handbook) — the open reference on getting content cited by AI answer engines (ChatGPT, Perplexity, Google AI Overviews, Gemini, Copilot).
- [notebooklm-kb-system](https://github.com/ferinazumaDEV/notebooklm-kb-system) — a token-efficient "second brain" for AI agents: local memory, NotebookLM notebooks, and knowledge routing.
- [politeclient](https://github.com/ferinazumaDEV/politeclient) — a polite, bulletproof HTTP client for Python: retries with backoff, per-host rate-limiting, and caching — handy for talking to LLM provider APIs.
- [scaffld](https://github.com/ferinazumaDEV/scaffld) — scaffold fully-wired Python projects (tests, CI, pre-commit, license) from templates.
- Hub & writing: [zentimes.es](https://zentimes.es).

By [ferinazumaDEV](https://github.com/ferinazumaDEV).

## License

MIT — see [LICENSE](LICENSE).

---

*Built by Fernando Aporta Franco ([@ferinazumaDEV](https://github.com/ferinazumaDEV)).*
