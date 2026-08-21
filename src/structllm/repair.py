"""Tolerant JSON repair.

LLMs routinely return *almost* JSON: wrapped in ```json fences, padded with a
"Sure, here you go" preamble, using Python's ``True``/``None``, trailing commas,
single quotes, unquoted keys, ``// comments`` — or simply cut off mid-object when
they hit the token limit. :func:`repair_json` turns that into a strictly valid
JSON string using a single-pass, string-aware scanner (no ``eval``, no network).

The scanner is deliberately conservative: strings are re-encoded through
``json.dumps`` so nothing inside them is corrupted, and it stops as soon as the
top-level value closes, ignoring any trailing prose.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from .errors import RepairError

__all__ = ["repair_json", "loads_repaired"]

_FENCE_RE = re.compile(
    r"```(?:json5?|javascript|js)?[ \t]*\r?\n?(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
# Characters that terminate a bareword / number token.
_DELIMS = set(" \t\r\n,:{}[]\"'`")
# Escape sequences understood inside strings (JSON plus a few lenient extras).
_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
    "/": "/", "\\": "\\", '"': '"', "'": "'", "`": "`", "\n": "",
}
_NULL_WORDS = {"null", "none", "nil", "undefined", "nan", "na"}


def loads_repaired(text: str) -> Any:
    """Repair *text* into valid JSON and return the parsed Python object."""
    return json.loads(repair_json(text))


def repair_json(text: str) -> str:
    """Return a strictly valid JSON string parsed from messy model output.

    Raises :class:`RepairError` if the input cannot be salvaged into JSON.
    """
    if not isinstance(text, str):
        raise RepairError(f"repair_json expects str, got {type(text).__name__}")

    stripped = _strip_code_fences(text).strip()

    # Fast path: already-valid JSON is returned untouched.
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    repaired = _Repairer(stripped).run()
    try:
        json.loads(repaired)
    except json.JSONDecodeError as exc:  # pragma: no cover - safety net
        raise RepairError(f"could not repair into valid JSON: {exc}") from exc
    return repaired


def _strip_code_fences(text: str) -> str:
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1)
    if "```" in text:
        return re.sub(r"```[A-Za-z0-9]*", "", text)
    return text


class _Repairer:
    """Single-pass, string-aware repairer. See module docstring."""

    def __init__(self, source: str):
        self.s = source
        self.n = len(source)
        self.i = 0
        self.out: List[str] = []
        self.stack: List[str] = []
        self.started = False

    def run(self) -> str:
        start = self._find_start()
        if start is None:
            # No container at all — best-effort a lone scalar (e.g. `True`, `'hi'`).
            return self._repair_scalar(self.s.strip())

        self.i = start
        while self.i < self.n:
            if self.started and not self.stack:
                break  # top-level value closed; ignore any trailing prose
            c = self.s[self.i]

            if c in " \t\r\n":
                self.i += 1
            elif c == "/" and self._peek(1) in "/*":
                self._skip_comment()
            elif c in "{[":
                self.started = True
                self.stack.append(c)
                self.out.append(c)
                self.i += 1
            elif c in "}]":
                self._strip_trailing_sep()
                if self.stack:
                    self.stack.pop()
                self.out.append(c)
                self.i += 1
            elif c in "\"'`":
                self._read_string()
            elif c in ",:":
                self.out.append(c)
                self.i += 1
            elif c in "+-" or c.isdigit() or (c == "." and self._peek(1).isdigit()):
                self._read_number()
            else:
                self._read_bareword()

        self._finalize()
        return "".join(self.out)

    # -- helpers ---------------------------------------------------------------

    def _peek(self, offset: int) -> str:
        j = self.i + offset
        return self.s[j] if 0 <= j < self.n else ""

    def _find_start(self) -> Optional[int]:
        for j, ch in enumerate(self.s):
            if ch in "{[":
                return j
        return None

    def _skip_comment(self) -> None:
        if self._peek(1) == "/":
            end = self.s.find("\n", self.i)
            self.i = self.n if end == -1 else end + 1
        else:  # /* ... */
            end = self.s.find("*/", self.i + 2)
            self.i = self.n if end == -1 else end + 2

    def _next_significant(self) -> str:
        """Peek at the next meaningful char after current position (skips space/comments)."""
        j = self.i
        while j < self.n:
            ch = self.s[j]
            if ch in " \t\r\n":
                j += 1
            elif ch == "/" and j + 1 < self.n and self.s[j + 1] in "/*":
                if self.s[j + 1] == "/":
                    nxt = self.s.find("\n", j)
                    j = self.n if nxt == -1 else nxt + 1
                else:
                    nxt = self.s.find("*/", j + 2)
                    j = self.n if nxt == -1 else nxt + 2
            else:
                return ch
        return ""

    def _read_string(self) -> None:
        quote = self.s[self.i]
        self.i += 1
        buf: List[str] = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\":
                nxt = self._peek(1)
                if nxt == "u" and self.i + 6 <= self.n:
                    hexs = self.s[self.i + 2 : self.i + 6]
                    try:
                        buf.append(chr(int(hexs, 16)))
                        self.i += 6
                        continue
                    except ValueError:
                        pass
                if nxt:
                    buf.append(_ESCAPES.get(nxt, nxt))
                    self.i += 2
                    continue
                self.i += 1  # trailing lone backslash
                break
            if c == quote:
                self.i += 1
                break
            buf.append(c)  # tolerate raw newlines inside the string
            self.i += 1
        self.out.append(json.dumps("".join(buf)))

    def _read_number(self) -> None:
        start = self.i
        if self.s[self.i] in "+-":
            self.i += 1
        while self.i < self.n and (self.s[self.i].isdigit() or self.s[self.i] in ".eE+-"):
            self.i += 1
        raw = self.s[start : self.i]
        norm = _normalize_number(raw)
        self.out.append(norm if norm is not None else json.dumps(raw))

    def _read_bareword(self) -> None:
        start = self.i
        while self.i < self.n and self.s[self.i] not in _DELIMS:
            if self.s[self.i] == "/" and self._peek(1) in "/*":
                break
            self.i += 1
        word = self.s[start : self.i]
        if not word:  # stray char we do not recognise; skip to stay progressing
            self.i += 1
            return
        if self._next_significant() == ":":
            self.out.append(json.dumps(word))  # unquoted object key
            return
        low = word.lower()
        if low == "true":
            self.out.append("true")
        elif low == "false":
            self.out.append("false")
        elif low in _NULL_WORDS:
            self.out.append("null")
        else:
            self.out.append(json.dumps(word))  # unquoted string value

    def _strip_trailing_sep(self) -> None:
        while self.out and self.out[-1] == ",":
            self.out.pop()
        if self.out and self.out[-1] == ":":
            self.out.append("null")  # key with no value

    def _finalize(self) -> None:
        self._strip_trailing_sep()
        # Truncated mid-key: `{"a":1,"b"` -> give the dangling key a null value.
        if (
            self.stack
            and self.stack[-1] == "{"
            and self.out
            and self.out[-1].startswith('"')
            and len(self.out) >= 2
            and self.out[-2] in ("{", ",")
        ):
            self.out.append(":")
            self.out.append("null")
        while self.stack:
            opener = self.stack.pop()
            self.out.append("}" if opener == "{" else "]")

    def _repair_scalar(self, text: str) -> str:
        if not text:
            raise RepairError("empty input")
        low = text.lower()
        if low == "true":
            return "true"
        if low == "false":
            return "false"
        if low in _NULL_WORDS:
            return "null"
        num = _normalize_number(text)
        if num is not None:
            return num
        if len(text) >= 2 and text[0] in "\"'`" and text[-1] in "\"'`":
            return json.dumps(text[1:-1])
        # Arbitrary prose with no container and no recognisable scalar is not JSON.
        raise RepairError("no JSON value found in input")


def _normalize_number(raw: str) -> Optional[str]:
    r = raw.strip().lstrip("+")
    if not r or r in ("-", ".", "-."):
        return None
    try:
        json.loads(r)
        return r
    except json.JSONDecodeError:
        pass
    try:
        return repr(float(r))
    except ValueError:
        return None
