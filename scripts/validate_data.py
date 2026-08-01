#!/usr/bin/env python3
"""Validate the provider registry and required maintenance files."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_PATH = ROOT / "data" / "providers.yml"
README_PATH = ROOT / "README.md"
REQUIRED_PROVIDER_FIELDS = {"id", "name", "source_heading", "url"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_registry(path: Path = PROVIDERS_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: document root must be a mapping")
    return data


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_registry(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("providers.yml: schema_version must be 1")

    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        return errors + ["providers.yml: providers must be a non-empty list"]

    readme = README_PATH.read_text(encoding="utf-8")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, provider in enumerate(providers, start=1):
        prefix = f"providers.yml: providers[{index}]"
        if not isinstance(provider, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        missing = REQUIRED_PROVIDER_FIELDS - provider.keys()
        if missing:
            errors.append(f"{prefix} missing fields: {', '.join(sorted(missing))}")
            continue

        provider_id = provider["id"]
        name = provider["name"]
        heading = provider["source_heading"]
        url = provider["url"]

        if not isinstance(provider_id, str) or not ID_PATTERN.fullmatch(provider_id):
            errors.append(f"{prefix}.id must use lowercase kebab-case")
        elif provider_id in seen_ids:
            errors.append(f"{prefix}.id is duplicated: {provider_id}")
        else:
            seen_ids.add(provider_id)

        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a non-empty string")
        elif name in seen_names:
            errors.append(f"{prefix}.name is duplicated: {name}")
        else:
            seen_names.add(name)

        if not isinstance(heading, str) or f"## {heading}\n" not in readme:
            errors.append(f"{prefix}.source_heading not found in README: {heading!r}")
        if url is not None and (not isinstance(url, str) or not _valid_http_url(url)):
            errors.append(f"{prefix}.url must be null or an http(s) URL")
    return errors


def validate_project() -> tuple[list[str], list[str], dict[str, Any]]:
    try:
        data = load_registry()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)], [], {}

    errors = validate_registry(data)
    for path in (
        ROOT / "LICENSE",
        ROOT / "NOTICE.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "docs" / "methodology.md",
    ):
        if not path.is_file():
            errors.append(f"missing required project file: {path.relative_to(ROOT)}")
    return errors, [], data


def main() -> int:
    errors, _, data = validate_project()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    providers = data["providers"]
    urls = sum(1 for provider in providers if provider["url"])
    print(f"Validation passed: {len(providers)} providers, {urls} URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
