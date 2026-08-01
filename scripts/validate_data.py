#!/usr/bin/env python3
"""Validate the structured provider registry and test-result ledger."""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_PATH = ROOT / "data" / "providers.yml"
RESULTS_PATH = ROOT / "data" / "test-results.csv"
README_PATH = ROOT / "README.md"

REQUIRED_PROVIDER_FIELDS = {
    "id",
    "name",
    "source_heading",
    "url",
    "status",
    "last_reviewed",
    "testing_status",
    "commercial_relationship",
}
ALLOWED_STATUSES = {"active", "inactive", "unknown"}
ALLOWED_TESTING_STATUSES = {"not_tested", "vendor_claims_only", "tested"}
ALLOWED_RELATIONSHIPS = {"affiliate", "sponsored", "none", "undisclosed"}
ALLOWED_RESULT_STATUSES = {"not_tested", "passed", "failed", "partial"}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_registry(path: Path = PROVIDERS_PATH) -> dict[str, Any]:
    """Load providers.yml and require a mapping at the document root."""
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: document root must be a mapping")
    return data


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_registry(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("providers.yml: schema_version must be 1")

    providers = data.get("providers")
    if not isinstance(providers, list) or not providers:
        errors.append("providers.yml: providers must be a non-empty list")
        return errors, warnings

    readme = README_PATH.read_text(encoding="utf-8")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    undisclosed_ids: list[str] = []

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

        url = provider["url"]
        if url is not None and (not isinstance(url, str) or not _valid_http_url(url)):
            errors.append(f"{prefix}.url must be null or an http(s) URL")

        if provider["status"] not in ALLOWED_STATUSES:
            errors.append(f"{prefix}.status must be one of {sorted(ALLOWED_STATUSES)}")
        if provider["testing_status"] not in ALLOWED_TESTING_STATUSES:
            errors.append(
                f"{prefix}.testing_status must be one of {sorted(ALLOWED_TESTING_STATUSES)}"
            )
        if provider["commercial_relationship"] not in ALLOWED_RELATIONSHIPS:
            errors.append(
                f"{prefix}.commercial_relationship must be one of "
                f"{sorted(ALLOWED_RELATIONSHIPS)}"
            )
        elif provider["commercial_relationship"] == "undisclosed":
            undisclosed_ids.append(provider_id)

        reviewed = provider["last_reviewed"]
        if reviewed is not None:
            if not isinstance(reviewed, str):
                errors.append(f"{prefix}.last_reviewed must be null or YYYY-MM-DD")
            else:
                try:
                    reviewed_date = date.fromisoformat(reviewed)
                    if reviewed_date > date.today():
                        errors.append(f"{prefix}.last_reviewed cannot be in the future")
                except ValueError:
                    errors.append(f"{prefix}.last_reviewed must use YYYY-MM-DD")

        if provider["testing_status"] == "tested" and reviewed is None:
            errors.append(f"{prefix}: tested providers require last_reviewed")

    if undisclosed_ids:
        warnings.append(
            f"{len(undisclosed_ids)} provider(s) need owner confirmation of commercial "
            "relationships: " + ", ".join(undisclosed_ids)
        )

    return errors, warnings


def validate_test_results(provider_ids: set[str]) -> list[str]:
    errors: list[str] = []
    required_columns = {
        "provider_id",
        "tested_at",
        "result_status",
        "evidence_url",
        "notes",
    }

    with RESULTS_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = required_columns - columns
        if missing_columns:
            return [
                "test-results.csv missing columns: "
                + ", ".join(sorted(missing_columns))
            ]
        rows = list(reader)

    seen_provider_ids: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        prefix = f"test-results.csv:{row_number}"
        provider_id = (row.get("provider_id") or "").strip()
        result_status = (row.get("result_status") or "").strip()
        tested_at = (row.get("tested_at") or "").strip()
        evidence_url = (row.get("evidence_url") or "").strip()

        if provider_id not in provider_ids:
            errors.append(f"{prefix}: unknown provider_id {provider_id!r}")
        else:
            seen_provider_ids.add(provider_id)

        if result_status not in ALLOWED_RESULT_STATUSES:
            errors.append(
                f"{prefix}: result_status must be one of {sorted(ALLOWED_RESULT_STATUSES)}"
            )

        if result_status != "not_tested":
            if not tested_at:
                errors.append(f"{prefix}: tested_at is required for an actual result")
            else:
                try:
                    date.fromisoformat(tested_at)
                except ValueError:
                    errors.append(f"{prefix}: tested_at must use YYYY-MM-DD")
            if not evidence_url or not _valid_http_url(evidence_url):
                errors.append(f"{prefix}: an http(s) evidence_url is required")

    missing_rows = provider_ids - seen_provider_ids
    if missing_rows:
        errors.append(
            "test-results.csv has no ledger row for: " + ", ".join(sorted(missing_rows))
        )
    return errors


def validate_project() -> tuple[list[str], list[str], dict[str, Any]]:
    try:
        data = load_registry()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)], [], {}

    errors, warnings = validate_registry(data)
    providers = data.get("providers", [])
    provider_ids = {
        item.get("id")
        for item in providers
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    errors.extend(validate_test_results(provider_ids))

    for required_path in (
        ROOT / "LICENSE",
        ROOT / "NOTICE.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "docs" / "methodology.md",
    ):
        if not required_path.is_file():
            errors.append(f"missing required project file: {required_path.relative_to(ROOT)}")

    return errors, warnings, data


def main() -> int:
    errors, warnings, data = validate_project()
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"Validation failed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    providers = data["providers"]
    urls = sum(1 for provider in providers if provider["url"])
    print(
        f"Validation passed: {len(providers)} providers, {urls} URLs, "
        f"{len(warnings)} disclosure warning(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
