# prepush ✈️

> Run your GitHub Actions workflow steps **locally, without Docker**, to catch CI failures *before* you push.

You know the loop: edit → commit → push → wait 3 minutes → CI fails on a typo → repeat. **prepush** breaks it. It reads your `.github/workflows/*.yml`, runs the `run:` steps right on your machine, expands `${{ ... }}` expressions, expands the build matrix, honors `if:` conditions and `env:` — and tells you in **seconds** whether your workflow's commands actually work.

```console
$ prepush
▶ CI / test (python=3.12)
  ✓ Lint  (0.31s)
  ✓ Unit tests  (1.84s)
  ✗ Build docs  (0.12s)  (exited with code 2)

Summary: FAILED — 2 passed, 1 failed, 0 warned, 1 skipped (4 steps)
```

## Why not just use `act`?

[`act`](https://github.com/nektos/act) is great when you need a faithful re-creation of the GitHub runner — but that fidelity is expensive: it needs **Docker**, pulls **multi-GB runner images** (the full image wants ~75 GB free), only emulates **Linux** runners, and is known to **hang on Apple Silicon**.

prepush makes the opposite trade. It does **not** virtualize the runner. It runs your steps' shell commands directly against your local toolchain, so it's:

- 🪶 **Dependency-light** — pure Python + PyYAML. No Docker, no images, no daemon.
- ⚡ **Instant** — runs your steps as fast as your shell does.
- 💻 **Cross-platform** — works wherever Python and a shell do (Linux, macOS, Windows/WSL).

The tradeoff is honest: prepush is a **fast pre-push sanity check**, not a perfect runner. It won't execute third-party `uses:` actions (it skips them with a clear note) — but it *will* catch the failures that actually bite you: broken commands, failing tests, lint errors, bad scripts, wrong env handling.

## Install

```bash
pip install prepush         # once published
# or from this repo:
pip install "git+https://github.com/shehanrao12-cpu/dolos.git#subdirectory=prepush"
```

## Usage

```bash
prepush                       # discover & run .github/workflows/*.yml
prepush path/to/workflow.yml  # run one workflow file
prepush --list                # show workflows, jobs, and steps
prepush --dry-run             # print what would run, run nothing
prepush --job build           # run only the "build" job
prepush --workflow ci         # only workflows whose name/file matches "ci"
prepush --keep-going          # don't stop a job at the first failing step
prepush --env API_URL=http://localhost:8080   # inject env vars
```

prepush exits **non-zero** if any step fails, so you can wire it into a git hook:

```bash
# .git/hooks/pre-push
#!/bin/sh
exec prepush --workflow ci
```

## What it supports

| Feature | Status |
| --- | --- |
| `run:` steps (bash / sh / python shells) | ✅ |
| `${{ ... }}` expressions (contexts, operators, common functions) | ✅ |
| `env:` at workflow / job / step level | ✅ |
| `strategy.matrix` (incl. `include` / `exclude`) | ✅ |
| `if:` conditions (`runner.os`, `matrix.*`, `success()`/`failure()`, ...) | ✅ |
| `working-directory`, `continue-on-error`, `defaults.run` | ✅ |
| `actions/checkout` | ✅ skipped (you're already in the tree) |
| Other `uses:` actions | ⏭️ skipped with a note (run-only mode) |
| Service containers, container jobs | ❌ out of scope by design |

### Supported expression functions

`success()`, `failure()`, `always()`, `cancelled()`, `contains()`, `startsWith()`,
`endsWith()`, `format()`, `join()`, `toJSON()`, `fromJSON()`. Contexts: `github`,
`env`, `matrix`, `runner`, `secrets`, `vars`, `job`, `steps`, `strategy`.

> Secrets/vars are read from your local environment as a best-effort substitute.
> Unsupported expression syntax degrades to an empty string rather than crashing.

## Try it

```bash
prepush examples/ci.yml
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
