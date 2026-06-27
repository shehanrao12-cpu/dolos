# debthawk 🦅

> Hunt down technical debt in your codebase — turn scattered `TODO`s and `FIXME`s into an actionable, scored report.

**debthawk** scans a source tree for debt markers (`TODO`, `FIXME`, `HACK`, `XXX`, `BUG`, ...), enriches each one with **git-blame author and age**, scores severity, flags **stale** debt that has been rotting for too long, and can **fail your CI** when debt crosses a threshold.

- 🚀 **Zero dependencies** — pure Python standard library, runs anywhere Python 3.11+ does.
- 🔍 **git-aware** — knows *who* wrote each marker and *how long* it has been there.
- 📊 **Multiple outputs** — colored terminal, Markdown, JSON, CSV.
- 🚦 **CI gating** — `--max-debt`, `--max-score`, `--fail-on-stale`.
- ⚙️ **Configurable** — custom tags/weights via `pyproject.toml` or `debthawk.toml`.

## Why?

Every codebase accumulates `TODO`s. The problem is never writing them — it's that they become invisible. debthawk makes the invisible measurable: a single number for how much debt you carry, who carries it, and which markers have gone stale. Drop it into CI and stop the pile from growing.

## Install

From source (no dependencies required to run):

```bash
git clone https://github.com/shehanrao12-cpu/dolos.git
cd dolos/debthawk
pip install .
```

Or run without installing:

```bash
python -m debthawk .
```

## Usage

```bash
# Scan the current directory (pretty terminal output)
debthawk

# Scan a specific path
debthawk src/

# Machine-readable output
debthawk --format json
debthawk --format markdown > DEBT.md
debthawk --format csv

# Only track certain tags, or add a custom one with a weight
debthawk --tag FIXME --tag BUG
debthawk --tag SECURITY=10

# Ignore paths
debthawk --ignore "tests/*" --ignore "*.min.js"

# Consider markers older than 90 days "stale"
debthawk --stale-days 90
```

### CI gating

`debthawk` exits non-zero when a gate is exceeded, so it slots straight into a pipeline:

```bash
# Fail the build if there are more than 50 markers
debthawk --max-debt 50

# Fail if the weighted debt score exceeds 100
debthawk --max-score 100

# Fail if any debt has gone stale
debthawk --fail-on-stale --stale-days 180
```

| Exit code | Meaning |
| --------- | ------- |
| `0` | Success / no gate exceeded |
| `1` | A gate (`--max-debt` / `--max-score` / `--fail-on-stale`) was exceeded |
| `2` | Usage error (e.g. path not found) |

## Configuration

debthawk reads `[tool.debthawk]` from `pyproject.toml` (or a standalone `debthawk.toml`, which takes precedence). CLI flags always win.

```toml
[tool.debthawk]
# Override or extend the default tag set and severity weights.
tags = { TODO = 2, FIXME = 5, HACK = 3, SECURITY = 10 }

# Glob patterns (relative to the scan root) to skip.
ignore = ["vendor/*", "*.generated.*"]

# Age (days) after which a marker is "stale".
stale_days = 180

# Score multiplier applied to stale markers.
stale_multiplier = 2.0

# Match tags case-insensitively (default: false).
case_sensitive = true

# Enrich findings with git blame (default: true).
blame = true
```

### Default tags & weights

| Tag | Weight | | Tag | Weight |
| --- | ------ |-| --- | ------ |
| `FIXME` | 5 | | `REFACTOR` | 2 |
| `BUG` | 5 | | `OPTIMIZE` | 2 |
| `XXX` | 4 | | `DEPRECATED` | 3 |
| `HACK` | 3 | | `NOTE` | 1 |
| `TODO` | 2 | | `REVIEW` | 1 |

## How scoring works

Each finding contributes its tag **weight** to the total debt score. If a finding is **stale** (older than `stale_days`, determined via `git blame`), its contribution is multiplied by `stale_multiplier`. The aggregate score gives you one comparable number to track over time and gate on in CI.

## GitHub Action example

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0   # needed for git-blame age data
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install git+https://github.com/shehanrao12-cpu/dolos.git#subdirectory=debthawk
- run: debthawk . --max-score 200 --fail-on-stale
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
