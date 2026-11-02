"""Column shorthands for migrations.

Every table repeats the same id and timestamp columns; spelling them out four
more times only makes the interesting parts of a migration harder to find.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

MONEY = sa.Numeric(18, 4)
QUANTITY = sa.Numeric(18, 4)


def uuid_pk() -> sa.Column:
    return sa.Column("id", PGUUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"))


def uuid_column(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, PGUUID(as_uuid=True), nullable=nullable)


def created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def updated_at() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def timestamps() -> tuple[sa.Column, sa.Column]:
    return created_at(), updated_at()


def money_column(name: str, *, default: str | None = "0", nullable: bool = False) -> sa.Column:
    """`default=None` for amounts the caller must always supply (unit prices).

    `nullable=True` is for amounts where "no value" is itself information --
    the total a scanned invoice line did not print, which is not zero.
    """
    return sa.Column(name, MONEY, nullable=nullable, server_default=default)


def quantity_column(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column:
    return sa.Column(name, QUANTITY, nullable=nullable, server_default=default)


def enum_column(name: str, values: tuple[str, ...], type_name: str, **kwargs) -> sa.Column:
    return sa.Column(
        name,
        sa.Enum(*values, name=type_name, native_enum=False, length=32),
        **kwargs,
    )
