# Design conventions

These principles require engineering judgment. Mechanical policy lives in
`pyproject.toml` and `prek.toml`; this document covers design choices that a
linter cannot decide reliably.

## Preserve plan-before-write boundaries

Resolve and validate a complete immutable plan before changing a target.
`RepoApplyPlan`, `HomePlan`, and `PublishPlan` are the established pattern:
planning code may inspect state, while a small apply boundary owns mutations.
Do not interleave discovery and writes in a loop when the full conflict set can
be found first.

## Prefer composition and protocols

Build workflows from focused operations and adapters instead of inheritance
trees or classes controlled by growing boolean flags. Use a `Protocol` when a
consumer needs only a narrow capability, as `HostCtxLike` and `RepoCtxLike` do.
Framework base classes, Pydantic models, exceptions, and genuine is-a
relationships remain appropriate uses of inheritance.

## Parse at system boundaries

Turn raw TOML, environment values, command input, Git output, and pyinfra data
into constrained values at the edge. Carry `RepoSettings`, `HostSettings`,
`Scope`, frozen dataclasses, and safe `Path` values through the rest of the
program instead of repeatedly validating raw strings and dictionaries.

A Pydantic validator that leaves a field typed as plain `str` does not give the
type checker evidence of a domain distinction. When downstream code must not
mix two string-shaped concepts, introduce a semantic type rather than relying
on repeated checks.

## Use semantic types where confusion is plausible

New identifiers should not default to anonymous `str` values when category
errors are realistic. Consider `NewType` or a frozen value object for repo IDs,
owner IDs, host names, and feature IDs. Use `Path` for filesystem paths and
`Scope` for host/repo scope. Do not wrap generic counters or display-only text
that has no domain identity.

Avoid a broad retrofit solely for consistency. Introduce a semantic type at a
boundary and migrate its consumers as one coherent change.

## Keep code and concrete documentation coupled

When prose repeats a concrete constant, environment variable, resolution
order, or on-disk schema, leave a `NOTE:` at the code site naming the document
and section. Changing either side requires checking the other in the same
change. Architectural overviews should explain stable boundaries rather than
mirror every function.

## Protect public behavior

Tests should enter through public CLI, logic, or model surfaces and assert
observable results. A private helper may be tested directly only when its sole
effect is an external-process side channel with no reachable public
observation; mark that import with the narrow prek exemption.
