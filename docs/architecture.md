# cfg architecture

## System boundary

cfg has two independent components:

```text
cfg tool                           private ~/.cfg personalization repository
------------------------------    ---------------------------------
CLI and configuration loading  -> host and repo inventory
validation and planning         -> features and dependencies
repo filesystem apply engine    -> overlays, mirrors, render inputs
pyinfra host runner             -> trusted host deploy files
generic documentation/tests     -> personal operational data
```

The tool never needs access to the private repository at build or publish time.
The private repository does not vendor the tool. Their contract is the current
configuration model and trusted deploy-file interface.

## Tool responsibilities

The tool repository owns:

- the `cfg` command;
- discovery and validation of a configuration root;
- host and repo models;
- feature dependency and conflict resolution;
- deterministic plan creation;
- safe, idempotent application;
- rendering and drift checks;
- pyinfra invocation for host workflows;

It must contain useful examples, but no real personal inventory or payloads.

## Package codemap

- `main.py`, `cfg/host/app.py`, and `cfg/repo/app.py` are Typer adapters. They
  parse command input and render the lines returned by the logic packages.
- `cfg/core/` owns shared schemas, safe-path parsing, root and identity
  discovery, persisted state, subprocess handling, and system checks.
- `cfg/core/owners/` loads feature manifests and resolves dependency order.
  Boundary Pydantic models are converted into immutable composed owner values;
  `cfg/owners/fs.py` maps those owners to overlay and mirror payloads.
- `cfg/repo/` owns repository identity, attachment, planning, and safe local
  filesystem changes. `cfg/repo/plan.py` is the write boundary.
- `cfg/render/` resolves repository templates and shared managed-file reports.
- `cfg/host/` owns host-facing command logic, managed-home plans, repository
  synchronization, and pyinfra deploy composition.
- `cfg/pyinfra/` is the pyinfra process boundary: it generates runtime
  inventory, invokes pyinfra, and cleans up transient inventory files.
- `cfg/deploys/host_data.py` is the narrow typed adapter for data exposed to
  trusted private deploy files.

The dependency graph is intentionally not a pure layer cake, but repo application and
host mutation are separate boundaries: a repo command never invokes a host workflow.

## Load-bearing invariants

- Typer adapters call `cfg.host.logic` or `cfg.repo.logic`; business logic does
  not import the app modules.
- Repository configuration is composed as `RepoOutputs`, then working-tree
  changes are fully validated as a `RepoApplyPlan` before `apply_repo_plan()`
  writes anything.
- All managed relative paths pass through `safe_relpath()` or an equivalent
  safe-path boundary before filesystem use.
- Cleanup removes a path only when cfg ownership can be established.
- The public repository never contains real personal inventory or payloads.
- Private `deploy.py` files are trusted extensions, not sandboxed input.

## Personalization repository

The default data root is `~/.cfg`.

```text
~/.cfg/
  cfg.toml
  hosts/
    <host>/
      cfg.toml
      overlay/
      mirror/
      render/
  repos/
    <owner>/<repo>/
      cfg.toml
      overlay/
      mirror/
      render/
  features/
    host/<feature>/
      feature.toml
      overlay/
      mirror/
      deploy.py
    repo/<feature>/
      feature.toml
      overlay/
      mirror/
      render/
```

Directory placement determines scope and management mode. Metadata does not repeat
the files already present under `overlay/` or `mirror/`.

Host and repo configuration use short, scope-local feature names:

```toml
features = ["linux", "i3", "claude"]
```

A feature manifest contains only information that cannot be inferred:

```toml
schema_version = 1
requires = ["base"]
conflicts = ["aerospace"]
generated = []
```

Repo features may declare explicit host prerequisites without exposing global owner IDs:

```toml
host_requires = ["uv"]
```

Generated outputs remain explicit because render inputs do not identify their
destination unambiguously:

```toml
generated = [".pre-commit-config.yaml"]
```

## Configuration-root discovery

Commands resolve the personalization root in this order:

1. `CFG_ROOT`;
2. the existing XDG cfg root pointer;
3. the nearest parent containing `.cfg-root`;
4. `~/.cfg`.

Commands must report the resolved root in debug/settings output. Missing or invalid roots
fail with actionable setup instructions; cfg never silently creates a new personal repo
during apply.

## Execution model

### Repo targets

Repo operations are direct local Python operations. A pure planning phase resolves all
sources, destinations, conflicts, prerequisites, and stale owned outputs before writes
begin. Dry-run prints that plan; apply executes it.

Mirrors and generated files share an atomic write operation containing captured
bytes and permissions. Overlay removal carries the exact recorded target;
unrecorded links are not automatically adopted for cleanup.

Pyinfra is not used for repo targets.

### Host targets

Pyinfra remains the host orchestration engine for packages, services, facts, local hosts,
and remote hosts. cfg invokes it through one supported subprocess path.

Private host features may contain trusted `deploy.py` code. The personalization
repository is trusted input with the user's privileges, so cfg does not pretend to
sandbox it. The tool exposes only the small context contract needed by those deploys.
Host-specific `hosts/<name>/deploy.py` entrypoints participate in the same resolved
owner sequence as host feature deploys.

`cfg host apply` applies home files, prepares sources for all enabled owners
through optional `prepare.py` entrypoints, then runs trusted deploys. Package refresh and upgrades
are an explicit second operation, `cfg host upgrade`, so routine configuration changes
do not perform unrelated system-wide mutation.

## Managed-file model

Three modes remain:

- **overlay**: symlink to canonical private-repo content;
- **mirror**: copy canonical bytes to the target;
- **generated**: render target bytes from templates and fragments.

The planner rejects multiple providers for the same destination unless the target config
selects one explicitly. Repo apply persists the last-applied owner, mode, and content
digest in the target's `.cfg/state.json`. Cleanup removes stale paths only while that
evidence still matches; modified paths produce a conflict instead.

Expanded per-host and per-repo manifests are not source data and have been removed. If
cleanup needs a last-applied inventory, cfg stores minimal local state rather than a
committed duplicate of the desired tree.

## Validation and testing

- Pydantic parses TOML and persisted state at system boundaries. Internal owner
  metadata is composed from frozen dataclasses and semantic repo, host, feature,
  and owner identifiers instead of passing raw dictionaries and interchangeable
  strings through the graph.
- `cfg validate` read-only parses the complete inventory, resolves every host and
  repository, renders configured generated outputs, and imports declared deploy
  entrypoints.
- Strict static checking remains enabled.
- The configured coverage percentage must not decrease.
- Tests should emphasize behavior and safety rather than imports, wrappers, or branch
  execution solely for coverage.

## Installation and release

The executable name is `cfg`. Install from a Git checkout until a distribution is
published. Packaging and publication do not change the tool-to-personalization boundary.
