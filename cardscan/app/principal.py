"""Request-scoped owner identity used by mutable application stores."""

from contextlib import contextmanager
from contextvars import ContextVar


REQUEST_OWNER = "__request__"
_owner = ContextVar("tallybinder_owner", default="local")


def current_owner():
    return _owner.get()


@contextmanager
def owner_scope(owner):
    token = _owner.set(str(owner))
    try:
        yield
    finally:
        _owner.reset(token)
