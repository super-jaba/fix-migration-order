# fix-migration-order

Rename Alembic migration files so they sort in chronological order.

## The problem

By default, Alembic names migration files using a random revision ID prefix (`<rev>_<slug>.py`), which means they appear in arbitrary order in your file browser:

```
01236043f642_add_tags.py          # created Mar 11
9c2e31367810_initial_schema.py    # created Mar 10  <-- should be first
f20d3f98e7d4_add_messages.py      # created Mar 18
```

Alembic's `file_template` setting fixes this for **new** migrations by prepending a date, but existing files keep their old names.

This tool renames all existing migrations to match your `file_template`, so old and new files follow the same naming scheme:

```
2026_03_10_1430-9c2e31367810_initial_schema.py
2026_03_11_1541-01236043f642_add_tags.py
2026_03_18_2352-f20d3f98e7d4_add_messages.py
```

Renaming is safe -- Alembic links revisions by internal IDs (`revision` / `down_revision`), not filenames.

## Requirements

- Python >= 3.12 (no third-party dependencies)

## Usage

### 1. Set `file_template` in your project's `alembic.ini`

Uncomment (or add) the `file_template` line under `[alembic]`:

```ini
[alembic]
file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
```

See the [Alembic docs](https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file) for all available tokens.

### 2. Run the script

The simplest way is to run `main.py` directly, pointing it at your project's config and migrations:

```bash
python /path/to/fix-migration-order/main.py \
  --alembic-config /path/to/your-project/alembic.ini \
  --alembic-migrations /path/to/your-project/alembic/versions
```

If your working directory is already the project root (where `alembic.ini` lives), the defaults apply and no flags are needed:

```bash
python /path/to/fix-migration-order/main.py
```

Add `--dry-run` to preview renames without touching the filesystem:

```bash
python /path/to/fix-migration-order/main.py --dry-run
```

If you installed the package (e.g. via `uv pip install`), you can use the `fix-migrations` command instead:

```bash
fix-migrations --dry-run
fix-migrations --alembic-config path/to/alembic.ini --alembic-migrations path/to/versions
```

### CLI reference

```
usage: fix-migration-order [-h] [--alembic-config PATH]
                           [--alembic-migrations PATH] [--dry-run]
```

| Flag | Default | Description |
|---|---|---|
| `--alembic-config PATH` | `./alembic.ini` | Path to your Alembic config file |
| `--alembic-migrations PATH` | `./alembic/versions` | Path to the migrations directory |
| `--dry-run` | off | Print renames without touching the filesystem |

## Supported template tokens

All tokens from Alembic's `file_template` are supported:

| Token | Example | Description |
|---|---|---|
| `%(rev)s` | `a1b2c3d4e5f6` | Revision ID |
| `%(slug)s` | `add_user_table` | Slugified revision message |
| `%(epoch)s` | `1710000000` | Unix timestamp of create date |
| `%(year)d` | `2026` | Year |
| `%(month).2d` | `03` | Zero-padded month |
| `%(day).2d` | `14` | Zero-padded day |
| `%(hour).2d` | `19` | Zero-padded hour |
| `%(minute).2d` | `59` | Zero-padded minute |
| `%(second).2d` | `09` | Zero-padded second |

## How it works

1. Reads `file_template` (and optionally `truncate_slug_length`) from `alembic.ini`
2. Recursively scans the migrations directory for `.py` files (supports both flat and subdirectory layouts)
3. Parses each file's docstring header to extract the revision ID, message, and create date
4. Generates the expected filename using the same algorithm as Alembic itself
5. Renames files that don't match (skips files that already do)
6. Cleans up empty subdirectories left behind after renames
