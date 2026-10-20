"""Configuration loading with a deliberately small, explicit surface."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, cast

# Load TOML support dynamically so static type checking also works when targeting
# Python 3.10, where the stdlib tomllib module is not available.
try:
    tomllib = cast(Any, importlib.import_module("tomllib"))
except ModuleNotFoundError:  # Python 3.10 compatibility backport
    tomllib = cast(Any, importlib.import_module("tomli"))


class ConfigError(ValueError):
    """Raised when project configuration cannot be read safely."""


def load_config(project: Path) -> dict[str, Any]:
    pyproject = project / "pyproject.toml"
    if not pyproject.exists():
        return {}
    try:
        with pyproject.open("rb") as handle:
            document = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not parse {pyproject}: {exc}") from exc
    tool_section = document.get("tool", {})
    if not isinstance(tool_section, dict):
        raise ConfigError("[tool] must be a TOML table")
    config = tool_section.get("pydistpilot", {})
    if not isinstance(config, dict):
        raise ConfigError("[tool.pydistpilot] must be a TOML table")
    imports = config.get("imports", [])
    if not isinstance(imports, list) or any(not isinstance(item, str) or not item.strip() for item in imports):
        raise ConfigError("[tool.pydistpilot].imports must be an array of non-empty strings")
    for module in imports:
        if any(not part.isidentifier() for part in module.split(".")):
            raise ConfigError(f"invalid import module in [tool.pydistpilot].imports: {module!r}")
    return config
