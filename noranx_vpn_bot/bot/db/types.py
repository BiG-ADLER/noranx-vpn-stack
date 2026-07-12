import enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=enum.Enum)


def pg_enum(enum_cls: type[E], name: str) -> SAEnum:
    """PostgreSQL native enum using Python enum values (lowercase), not names."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda x: [e.value for e in x],
    )
