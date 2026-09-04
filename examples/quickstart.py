"""typedout quickstart — runs fully offline against the MockProvider.

    python examples/quickstart.py

Shows the three things typedout is for:
  1. repairing + validating messy model output into a typed object,
  2. recovering from a schema-violating answer via an error-aware retry,
  3. streaming a partial object as it fills in, plus cost tracking.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from typedout import MockProvider, TypedOut, extract


class Person(BaseModel):
    name: str
    age: int = Field(ge=0)
    email: str


def demo_repair_and_validate() -> None:
    print("1) repair + validate messy output")
    # The mock returns JSON wrapped in a ```json fence with a trailing comma.
    llm = TypedOut(MockProvider(script=["fenced"]))
    person = llm.extract(Person, "Ada Lovelace, 36, ada@example.com")
    print(f"   -> {person!r}")
    print(f"   attempts={llm.last_attempts}  usage=({llm.last_usage})\n")


def demo_retry_on_invalid() -> None:
    print("2) recover from a schema violation with a retry")
    # First reply violates the schema; typedout feeds the error back and retries.
    llm = TypedOut(MockProvider(script=["invalid", "valid"], model="gpt-4o-mini"),
                    model="gpt-4o-mini")
    person = llm.extract(Person, "Ada Lovelace, 36, ada@example.com")
    print(f"   -> {person!r}")
    print(f"   attempts={llm.last_attempts}  cost=${llm.last_usage.cost_usd:.6f}\n")


def demo_streaming() -> None:
    print("3) stream a partial object as it fills in")
    llm = TypedOut(MockProvider(script=["valid"], chunk_size=8))
    for partial in llm.stream(Person, "Ada Lovelace, 36, ada@example.com"):
        print(f"   partial: {partial}")
    print(f"   final (validated): {llm.last_result!r}\n")


def demo_decorator() -> None:
    print("4) @extract decorator = a typed extractor function")

    @extract(Person, provider=MockProvider(script=["valid"]))
    def parse_person(text: str) -> Person:
        return f"Extract the person described here:\n{text}"

    print(f"   -> {parse_person('Ada Lovelace, 36, ada@example.com')!r}")


if __name__ == "__main__":
    demo_repair_and_validate()
    demo_retry_on_invalid()
    demo_streaming()
    demo_decorator()
