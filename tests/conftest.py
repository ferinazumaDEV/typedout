"""Shared fixtures: a couple of pydantic schemas the tests reuse."""

from __future__ import annotations

from typing import List, Optional

import pytest
from pydantic import BaseModel, Field


class Person(BaseModel):
    name: str
    age: int = Field(ge=0)
    email: str


class Address(BaseModel):
    city: str
    country: str


class Company(BaseModel):
    name: str
    employees: int
    hq: Address
    tags: List[str] = Field(default_factory=list)
    website: Optional[str] = None


@pytest.fixture
def person_cls():
    return Person


@pytest.fixture
def company_cls():
    return Company
