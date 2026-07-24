# cfg

`cfg` applies host and repository configuration from a separate personalization
repository.

The tool owns configuration loading, validation, dependency resolution, planning,
safe filesystem changes, and host orchestration. Personal inventory, payloads, and
trusted deploy files stay outside this repository.

## Install

Until a package is published, install directly from a Git checkout:

```bash
uv tool install /path/to/cfg
```

For tool development:

```bash
uv sync --group test
uv run pytest
uv tool install --editable .
```

## Personalization repository

By convention, personal configuration lives at `~/.cfg`:

```text
~/.cfg/
  .cfg-root
  hosts/
  repos/
  features/
    host/
    repo/
```

See [`examples/personalization`](examples/personalization) for a minimal synthetic
configuration.

`cfg` resolves the personalization root in this order:

1. `CFG_ROOT`;
2. the path stored in `$XDG_CONFIG_HOME/cfg/root`;
3. the nearest parent containing `.cfg-root`;
4. `~/.cfg`.

## Use

```bash
cfg host current
cfg host settings
cfg host managed
cfg host apply --dry-run

cfg repo settings
cfg repo apply --dry-run

cfg validate
```

Host operations use pyinfra. Repo operations build and execute a deterministic local
filesystem plan. Private `deploy.py` files are trusted Python extensions and run with
the user's privileges. `cfg host apply` is intentionally the one-shot host update:
it applies managed files and deploys, refreshes package metadata, and upgrades packages.

`cfg validate` parses and resolves the complete personalization repository without
writing to hosts, repositories, or the configuration root.

## Documentation

- [Architecture](docs/architecture.md)
- [Design conventions](CONVENTIONS.md)
- [Generated files](docs/generated-files.md)
- [pyinfra conventions](docs/pyinfra-idioms.md)
- [`stat` compatibility](docs/pyinfra-stat-hang-fix.md)
- [Quality scorecard](docs/QUALITY.md)
