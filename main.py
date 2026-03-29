#!/usr/bin/env python3
"""Rename Alembic migration files to match the configured file_template,
ensuring they sort in chronological order.
"""

import argparse
import configparser
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import TypedDict

_SLUG_RE = re.compile(r"\w+")

_DEFAULT_CONFIG = "./alembic.ini"
_DEFAULT_MIGRATIONS = "./alembic/versions"
_DEFAULT_TRUNCATE_SLUG_LENGTH = 40
_DEFAULT_FILE_TEMPLATE = "%(rev)s_%(slug)s"


class MigrationMetadata(TypedDict):
    message: str
    revision_id: str
    create_date_str: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fix-migration-order",
        description=(
            "Rename Alembic migration files to match the configured "
            "file_template, ensuring they appear in chronological order."
        ),
    )
    parser.add_argument(
        "--alembic-config",
        default=_DEFAULT_CONFIG,
        metavar="PATH",
        help=f"path to alembic.ini (default: {_DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--alembic-migrations",
        default=_DEFAULT_MIGRATIONS,
        metavar="PATH",
        help=f"path to the migrations versions directory (default: {_DEFAULT_MIGRATIONS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be renamed without performing any changes",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Config reading
# ---------------------------------------------------------------------------


def read_config(config_path: Path) -> tuple[str, int]:
    """Read ``file_template`` and ``truncate_slug_length`` from *alembic.ini*.

    Returns ``(file_template, truncate_slug_length)``.
    """
    parser = configparser.RawConfigParser()
    if not parser.read(str(config_path)):
        raise FileNotFoundError(f"Could not read config: {config_path}")

    if not parser.has_option("alembic", "file_template"):
        raise ValueError(
            f"file_template is not set in [alembic] section of {config_path}"
        )

    # RawConfigParser preserves ``%%`` literally – undo the escaping that
    # alembic.ini applies for ConfigParser compatibility.
    template = parser.get("alembic", "file_template").replace("%%", "%")

    truncate_slug_length = _DEFAULT_TRUNCATE_SLUG_LENGTH
    if parser.has_option("alembic", "truncate_slug_length"):
        truncate_slug_length = parser.getint("alembic", "truncate_slug_length")

    return template, truncate_slug_length


# ---------------------------------------------------------------------------
# Migration file parsing
# ---------------------------------------------------------------------------


def parse_migration(filepath: Path) -> MigrationMetadata | None:
    """Extract revision metadata from a migration file's top docstring.

    Expected layout (standard Alembic header)::

        \"""<message>

        Revision ID: <id>
        Revises: <parent_id>
        Create Date: <datetime>

        \"""

    Returns a dict with ``message``, ``revision_id``, ``create_date_str``
    or *None* when the file cannot be parsed.
    """
    content = filepath.read_text(encoding="utf-8")

    match = re.match(r'"""(.*?)"""', content, re.DOTALL)
    if not match:
        return None

    docstring = match.group(1).strip()
    lines = docstring.split("\n")

    message = lines[0].strip()
    revision_id: str | None = None
    create_date_str: str | None = None

    for line in lines[1:]:
        line = line.strip()
        if line.startswith("Revision ID:"):
            revision_id = line.split(":", 1)[1].strip()
        elif line.startswith("Create Date:"):
            create_date_str = line.split(":", 1)[1].strip()

    if not revision_id or not create_date_str:
        return None

    return MigrationMetadata(
        message=message,
        revision_id=revision_id,
        create_date_str=create_date_str,
    )


# ---------------------------------------------------------------------------
# Filename generation  (mirrors alembic.script.base.ScriptDirectory._rev_path)
# ---------------------------------------------------------------------------


def make_slug(message: str, truncate_slug_length: int) -> str:
    """Generate a slug from *message*, matching Alembic's algorithm exactly."""
    slug = "_".join(_SLUG_RE.findall(message or "")).lower()
    if len(slug) > truncate_slug_length:
        slug = slug[:truncate_slug_length].rsplit("_", 1)[0] + "_"
    return slug


def parse_create_date(date_str: str) -> datetime:
    """Parse a ``Create Date`` value, with or without microseconds."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str!r}")


def build_filename(
    template: str,
    metadata: MigrationMetadata,
    truncate_slug_length: int,
) -> str:
    """Render a new migration filename from *template* and parsed *metadata*."""
    dt = parse_create_date(metadata["create_date_str"])
    slug = make_slug(metadata["message"], truncate_slug_length)

    values: dict[str, str | int] = {
        "rev": metadata["revision_id"],
        "slug": slug,
        "epoch": int(dt.timestamp()),
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "hour": dt.hour,
        "minute": dt.minute,
        "second": dt.second,
    }

    return (template % values) + ".py"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _remove_empty_dirs(root: Path) -> None:
    """Remove empty subdirectories under *root* (bottom-up), leaving *root* itself."""
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            dirpath.rmdir()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    config_path = Path(args.alembic_config)
    migrations_path = Path(args.alembic_migrations)

    if not config_path.is_file():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    if not migrations_path.is_dir():
        print(
            f"Error: migrations directory not found: {migrations_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    template, truncate_slug_length = read_config(config_path)

    migration_files = sorted(migrations_path.rglob("*.py"))
    if not migration_files:
        print("No migration files found.")
        return

    renames: list[tuple[Path, Path]] = []
    skipped: list[str] = []

    for filepath in migration_files:
        metadata = parse_migration(filepath)
        if metadata is None:
            skipped.append(str(filepath.relative_to(migrations_path)))
            continue

        new_name = build_filename(template, metadata, truncate_slug_length)

        new_path = migrations_path / new_name
        if filepath == new_path:
            continue

        renames.append((filepath, new_path))

    if skipped:
        print(
            f"Warning: skipped {len(skipped)} file(s) (could not parse metadata):",
            file=sys.stderr,
        )
        for name in skipped:
            print(f"  {name}", file=sys.stderr)

    if not renames:
        print("All files already match the template. Nothing to rename.")
        return

    label = "Would rename" if args.dry_run else "Renamed"

    for old_path, new_path in renames:
        old_rel = old_path.relative_to(migrations_path)
        new_rel = new_path.relative_to(migrations_path)
        if args.dry_run:
            print(f"  {old_rel} -> {new_rel}")
        else:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            old_path.rename(new_path)
            print(f"  {old_rel} -> {new_rel}")

    if not args.dry_run:
        _remove_empty_dirs(migrations_path)

    print(f"\n{label} {len(renames)} file(s).")


if __name__ == "__main__":
    main()
