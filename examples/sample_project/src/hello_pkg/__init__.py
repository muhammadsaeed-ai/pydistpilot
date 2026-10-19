"""Example module for testing a built wheel."""

__version__ = "0.1.0"


def greeting(name: str = "developer") -> str:
    """Return a small deterministic greeting."""
    return f"Hello, {name}!"
