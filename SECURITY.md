# Security policy

## Supported versions

The distribution is **`typedout-py`** (the import stays `typedout`). Only the latest release is
supported; fixes land on `main` and there are no backport branches.

| Version | Supported |
| --- | --- |
| 0.1.x | yes |
| older | no |

## Reporting a problem

Please report privately first.

1. Preferred: GitHub's private vulnerability reporting on this repository — **Security → Report a
   vulnerability** ([direct link](https://github.com/ferinazumaDEV/typedout/security/advisories/new)).
2. If that form is not available to you,
   [open an issue](https://github.com/ferinazumaDEV/typedout/issues) saying only that you have a
   security report and how to reach you. **Do not put exploit details, prompts containing real data,
   or API keys in a public issue** — a private channel will be arranged from there.

Expect a first reply within a week. This is a small project maintained in spare time, so there is no
formal SLA and no bug bounty.

The most useful things to include are the `typedout-py` and Python versions, which provider you were
using, a minimal reproduction, and what an attacker gains.

## Your API key

**typedout never reads, stores, logs or transmits it.** `AnthropicProvider` and `OpenAIProvider` take
an optional `api_key=` and hand it straight to the vendor SDK; pass nothing and the SDK reads its own
environment variable, exactly as it would without typedout. There is no config file, no cache and no
credential of any kind on disk.

## Model output is treated as data, never as code

This is the property to check first in a library whose job is turning model text into Python objects:

- There is **no `eval`, `exec`, `literal_eval`, `pickle` or `__import__`** anywhere in the package.
- `repair_json` is a hand-written, string-aware scanner that closes brackets, strips code fences and
  fixes trailing commas. It rewrites text into valid JSON; it never executes it.
- Validation is `pydantic` (or a small JSON Schema checker for raw dicts). A field typed `str` gets a
  `str`, whatever the model tried to return.

## What validation does and does not promise

`typedout` guarantees the **shape** of the result, not its **truth**. If your prompt embeds text from
somewhere you do not control — a scraped page, a user upload, an email — that text can steer the
model, and a steered model can return something that validates perfectly and is entirely wrong. Treat
an extracted object as untrusted input to whatever comes next: it is well-typed, not verified.

Two smaller consequences worth knowing:

- **`last_raw` carries the raw model output.** `ValidationFailure` keeps the last response on
  `.last_raw` so you can debug a failure. That string reaches your logs and tracebacks like any other
  exception attribute, and it contains whatever the model said about your input.
- **Failures cost money.** When parsing or validation fails, the concrete errors are fed back and the
  call is retried, up to `max_retries` (default 2). A hostile or malformed input can therefore triple
  the token spend of a single `extract()`. Lower `max_retries` for untrusted workloads and watch
  `llm.last_usage`.

## Network and telemetry

typedout opens no connections of its own and sends no telemetry. The only traffic is the vendor SDK
calling its own API, under that SDK's own proxy, TLS and retry settings. `MockProvider` makes no
network calls at all, which is why the tests and examples run fully offline.

## Out of scope

Reports that a caller can hurt themselves — passing a hostile string as your own system prompt,
logging `last_raw` into a public place, or trusting an extracted object without checking it against
reality — are documentation issues rather than vulnerabilities. They are still welcome as issues.
