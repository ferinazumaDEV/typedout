#!/usr/bin/env python3
"""Does the installed package actually work?

Run against a freshly installed wheel or sdist — never against the repository —
so it answers the only question a release cares about: if somebody runs
`pip install typedout-py` right now, do they get something that functions?

    python scripts/smoke.py

Offline by design: MockProvider makes no network calls, so this needs no API
key and can run in CI, in a release pipeline, and on a stranger's laptop.

Exits non-zero on the first thing that does not hold.
"""

from __future__ import annotations

import importlib.metadata
import sys

DISTRIBUTION = "typedout-py"   # what you install
IMPORT_NAME = "typedout"       # what you import — deliberately different, see README


def main() -> int:
    # 1. It imports at all, by the name the docs promise.
    import typedout
    from pydantic import BaseModel
    from typedout import MockProvider, TypedOut

    # 2. The version the code reports and the version pip installed agree.
    #    This is where a botched release shows up: metadata from one build,
    #    code from another.
    installed = importlib.metadata.version(DISTRIBUTION)
    if typedout.__version__ != installed:
        print(f"FAIL  __version__ is {typedout.__version__} but "
              f"{DISTRIBUTION} metadata says {installed}")
        return 1
    print(f"ok    {DISTRIBUTION} {installed}, imported as {IMPORT_NAME}")

    # 3. Every name the package advertises resolves. A wheel that ships a
    #    truncated package still imports; this catches that.
    missing = [n for n in typedout.__all__ if not hasattr(typedout, n)]
    if missing:
        print(f"FAIL  __all__ advertises names that do not exist: {missing}")
        return 1
    print(f"ok    all {len(typedout.__all__)} public names resolve")

    # 4. The thing it exists to do, end to end, offline.
    class Person(BaseModel):
        name: str
        age: int

    provider = MockProvider(responses=['{"name": "Ada", "age": 36}'])
    person = TypedOut(provider).extract(Person, "give me a person")

    if not isinstance(person, Person) or person.name != "Ada" or person.age != 36:
        print(f"FAIL  extraction returned {person!r}")
        return 1
    print(f"ok    extraction returned a validated {type(person).__name__}: {person}")

    # 5. Tolerant repair is the feature people install this for; a build that
    #    dropped it would still pass everything above.
    from typedout import repair_json

    repaired = repair_json('```json\n{"a": 1,}\n```')
    if repaired.strip() not in ('{"a": 1}', '{"a":1}'):
        print(f"FAIL  repair_json produced {repaired!r}")
        return 1
    print("ok    repair_json strips fences and trailing commas")

    print("\nsmoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
