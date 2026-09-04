"""Incremental parsing of a streamed JSON object.

As chunks arrive they are appended to a buffer and the buffer is repaired+parsed
on every step. Because the repairer closes unbalanced braces, a half-received
object still parses — so callers see the object *fill in* field by field. Only
distinct snapshots are yielded, so a consumer can render live progress cheaply.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator

from .errors import RepairError
from .repair import loads_repaired


def iter_partial(chunks: Iterable[str]) -> Iterator[Any]:
    """Yield successive best-effort parses of a growing stream of text chunks.

    Chunks that do not yet contain any parseable JSON are skipped silently; each
    yielded value differs from the previous one.
    """
    buffer = ""
    previous: Any = _UNSET
    for chunk in chunks:
        buffer += chunk
        try:
            snapshot = loads_repaired(buffer)
        except RepairError:
            continue
        if snapshot != previous:
            previous = snapshot
            yield snapshot


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover
        return "<unset>"


_UNSET = _Unset()
