# Idiomatic pyinfra in cfg

Conventions and gotchas for writing pyinfra deploys in a cfg personalization repository.

## Use dedicated operations instead of `server.shell`

pyinfra operations are **idempotent** — they check current state via facts
before acting. `server.shell` always executes. Prefer the real operation:

```python
# Bad: always runs, hardcodes username
server.shell(commands=["usermod -aG docker alice"], _sudo=True)

# Good: only runs usermod when the user isn't already in the group
from pyinfra.facts.server import User
current_user = host.get_fact(User)
server.user(user=current_user, groups=["docker"], _sudo=True)
```

Common replacements:

| Instead of `server.shell` with... | Use operation |
|-----------------------------------|--------------|
| `usermod -aG` | `server.user(groups=[...])` |
| `apt-get install` | `apt.packages(packages=[...])` |
| `systemctl restart` | `server.service(restarted=True)` |
| `ln -sf` | `files.link(symbolic=True)` |
| `mkdir -p` | `files.directory()` |
| `chmod` / `chown` | `files.file(mode=..., user=..., group=...)` |
| `git clone` / `git pull` | `git.repo(src=..., dest=..., pull=True)` |

`server.shell` is still the right choice when there's no pyinfra operation
(e.g. snap commands, curl-pipe-to-sh installers, font cache rebuilds).

## Use global arguments instead of shell workarounds

pyinfra global arguments work across all connectors (local, SSH, Docker).

```python
# Bad
server.shell(commands=[f"cd {source_dir} && make install"])

# Good
server.shell(commands=["make install"], _chdir=source_dir)
```

## Use facts instead of hardcoding host state

```python
# Bad: breaks on any machine that isn't "decal"'s
server.shell(commands=["usermod -aG docker alice"])

# Good
from pyinfra.facts.server import User
current_user = host.get_fact(User)
server.user(user=current_user, groups=["docker"], _sudo=True)
```

Other useful facts: `Which` (command existence), `Home` (home dir),
`Command` (arbitrary shell output), `File` / `Link` (file metadata).

## `server.shell` runs each list element in a separate shell

pyinfra yields each command individually. Each one gets its own
`sh -c '<command>'` invocation. **Shell state does not persist between
list elements:**

```python
# Bug: WORK is set in one shell, used in a completely separate shell
server.shell(commands=["WORK=$(mktemp -d)", "cp config.toml $WORK/ && run-build $WORK"])

# Fix: single command string so they share a shell
server.shell(commands=["WORK=$(mktemp -d); cp config.toml $WORK/ && run-build $WORK"])
```

## For pipe safety, use `_shell_executable="bash"`

pyinfra has no built-in strict shell mode. `set -e` does not catch pipe
failures — only bash's `pipefail` does. Use `_shell_executable="bash"` with
`set -euo pipefail` for commands that pipe:

```python
server.shell(
    commands=['set -euo pipefail; curl -LsSf "..." | sh'],
    _shell_executable="bash",
)
```

## Use `signed-by` keyrings instead of `apt.key()`

`apt.key()` wraps the deprecated `apt-key` command. On modern Debian/Ubuntu,
`apt-key` may not be installed, causing `AptKeys` to return `None` and
`apt.key()` to crash with `TypeError: argument of type 'NoneType' is not
iterable`. pyinfra has no replacement operation — use `ensure_apt_repo()`
from `cfg.host.deploys.ensure`:

```python
# Bad: uses deprecated apt-key, crashes when apt-key is missing
apt.key(src="https://repo.example.com/gpg/key.asc", _sudo=True)
apt.repo(src="deb https://repo.example.com/deb stable main", filename="example", _sudo=True)

# Good: use ensure_apt_repo helper
from cfg.host.deploys.ensure import ensure_apt_repo

ensure_apt_repo(
    key_url="https://repo.example.com/gpg/key.asc",
    key_name="example",
    repo_src="deb https://repo.example.com/deb stable main",
    repo_filename="example",
)

# With extra repo options (e.g. arch pinning):
ensure_apt_repo(
    key_url="https://apt.releases.hashicorp.com/gpg",
    key_name="hashicorp",
    repo_src=f"deb https://apt.releases.hashicorp.com {codename} main",
    repo_filename="hashicorp",
    repo_options="arch=amd64",
)
```

The helper downloads the key to `/etc/apt/keyrings/<key_name>.gpg`, dearmors it,
and adds the repo with `[signed-by=...]`. The `File` fact check makes the
download idempotent across re-runs.

**Permissions gotcha:** `gpg --dearmor` inherits the current umask, which can
produce keyring files with restrictive permissions (e.g. 0600). If `apt` can't
read the keyring, `apt update` silently fails to verify the repo's signatures.
The helper explicitly `chmod 644`s the keyring and sets `mode="0644"` on the
sources list file to ensure both are world-readable.

## Structure conventions

- Deploy functions use the `@deploy("name")` decorator
- Each feature deploy lives at `features/host/<name>/deploy.py`
- Each feature deploy exposes a `main()` entry point
- Host-specific deploys live at `hosts/<hostname>/deploy.py`
- Use `_sudo=True` at the **operation level**, not globally via `Config.SUDO`
- Use facts for conditional logic (`Which`, `Home`, `File`, `Command`)
- Reuse `ensure_command()` from `cfg.host.deploys.pkg` for simple
  "ensure binary exists" patterns (cross-platform: apt on Linux, brew on macOS)

## Source preparation

Move third-party source setup from `deploy.py` into an optional `prepare.py`
beside it, with the same `main()` entrypoint. Both feature and host-specific
owners support this file. During `cfg host apply`, all enabled owners prepare
in dependency order before any owner deploy runs. `cfg host upgrade` also runs
preparation before refreshing package metadata.

Keep preparation limited to source reconciliation; do not install packages or
refresh package metadata there. Use `ensure_apt_repo()` to write the desired
source line before unrelated package operations can encounter an obsolete one.
Existing calls inside `deploy.py` still work but do not run early; move them to
`prepare.py` to obtain that ordering. Key-download tools must already be available.

Retire a source explicitly, using its complete previous contents:

```python
from cfg.host.deploys.ensure import remove_apt_repo


def main():
    remove_apt_repo(
        repo_filename="retired-example",
        expected_content="deb [signed-by=/etc/apt/keyrings/example.gpg] https://repo.example.com old main\n",
    )
```

Only that named regular file is removed, and only if its SHA-256 matches the
expected contents. Missing files are a no-op; modified files cause a conflict.
There is no reachability sweep: DNS failures, HTTP errors, and a shared keyring
location do not authorize deleting an APT source. To retire a disabled feature's
source, keep the explicit retirement in an enabled owner's preparation file.
