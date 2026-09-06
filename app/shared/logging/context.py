"""Per-request context propagated to log records without threading it through
every function signature."""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
company_id_var: ContextVar[str | None] = ContextVar("company_id", default=None)
