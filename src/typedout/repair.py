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
# Barewords with no JSON representation. The three non-finite floats live here
# for the same reason as the rest: RFC 8259 has no literal for them, and null is
# the only answer that does not invent data. "NaN" already behaved this way; the
# other two used to come out as the STRING "Infinity", silently turning a number
# into text.
_NULL_WORDS = {
    "null", "none", "nil", "undefined", "na",
    "nan", "-nan", "+nan",
    "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity",
}


def loads_repaired(text: str) -> Any:
    """Repair *text* into valid JSON and return the parsed Python object."""
    return json.loads(repair_json(text))


def repair_json(text: str) -> str:
    """Return a strictly valid JSON string parsed from messy model output.

    Valid JSON is returned unchanged -- including when one of its string values
    contains backticks or a Markdown code fence. Fences are only removed once
    the input has been found *not* to be valid JSON.

    "Strictly valid" excludes ``NaN``, ``Infinity`` and ``-Infinity``, which
    Python's ``json`` accepts but RFC 8259 has no syntax for. They repair to
    ``null``, like every other bareword this scanner cannot represent.

    Raises :class:`RepairError` if the input cannot be salvaged into JSON.
    """
    if not isinstance(text, str):
        raise RepairError(f"repair_json expects str, got {type(text).__name__}")

    original = text.strip()

    # Fast path, and it runs on the UNTOUCHED input on purpose. This used to
    # strip fences first, which meant a valid object whose string value happened
    # to contain ```json ... ``` was replaced by whatever sat between those
    # backticks, and one containing ```python ... ``` raised instead. Repairing
    # something that needed no repair is the worst thing this function can do,
    # so validity is asked before anything is removed.
    try:
        _strict_loads(original)
        return original
    except (json.JSONDecodeError, ValueError):
        pass

    # Only now: the input is not valid JSON, so an outer Markdown wrapper is a
    # plausible reason and removing it cannot destroy a well-formed value.
    stripped = _strip_code_fences(text).strip()
    if stripped != original:
        try:
            _strict_loads(stripped)
            return stripped
        except (json.JSONDecodeError, ValueError):
            pass

    repaired = _Repairer(stripped).run()
    try:
        _strict_loads(repaired)
    except (json.JSONDecodeError, ValueError) as exc:  # pragma: no cover - safety net
        raise RepairError(f"could not repair into valid JSON: {exc}") from exc
    return repaired


def _reject_non_finite(name: str) -> Any:
    """Refuse the three constants Python accepts and JSON has no syntax for."""
    raise ValueError(f"{name} is not valid JSON (RFC 8259 has no such literal)")


def _strict_loads(candidate: str) -> Any:
    """``json.loads`` without Python's non-finite extensions.

    ``json.loads`` accepts ``NaN``, ``Infinity`` and ``-Infinity`` by default.
    They are not JSON, so a string containing them must not be reported as
    already valid, nor returned as a repaired result. This function is what
    makes "a strictly valid JSON string" true rather than nearly true.
    """
    return json.loads(candidate, parse_constant=_reject_non_finite)


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
        if norm is not None:
            self.out.append(norm)
            return
        # A leading sign got us here, but what follows is not a number:
        # "-Infinity" used to stop after the "-" and emit `"-""Infinity"`, which
        # is not JSON at all. Take the rest of the token and let the bareword
        # rules decide what it means.
        while self.i < self.n and self.s[self.i] not in _DELIMS:
            self.i += 1
        word = self.s[start : self.i]
        if word.lower() in _NULL_WORDS:
            self.out.append("null")
        else:
            self.out.append(json.dumps(word))

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
        value = json.loads(r, parse_constant=_reject_non_finite)
    except (json.JSONDecodeError, ValueError):
        pass
    else:
        return r if isinstance(value, (int, float)) else None
    try:
        number = float(r)
    except ValueError:
        return None
    # float() happily returns inf and nan for "Infinity", "-Infinity" and "NaN",
    # and repr() then emits "inf" / "-inf" / "nan" -- none of which any JSON
    # parser accepts. There is no JSON number for these, so they are not numbers.
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return repr(number)
