"""Email value object: validated and normalised at construction time."""

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MAX_EMAIL_LENGTH = 320


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        normalised = self.value.strip().lower()
        if len(normalised) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(normalised):
            raise ValueError(f"Invalid email address: {self.value!r}")
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value
