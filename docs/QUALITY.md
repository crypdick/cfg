# Quality scorecard

This scorecard records the strictify baseline and the next useful quality
ratchets. Grades combine branch coverage, static typing, complexity, and test
health; they are not a substitute for reviewing behavior.

| Area | Grade | Coverage | Assessment |
| --- | --- | ---: | --- |
| `cfg/core` | A | 93.8% | Strictly typed, broadly tested, and mostly low-complexity. System checks contain the largest remaining coverage gap. |
| `cfg/core/owners` and `cfg/owners` | A | 93.0%+ | Dependency and payload resolution have strong behavioral coverage. |
| `cfg/repo` | A- | 90.4% | Plan-before-write boundaries are explicit; branch-heavy conflict handling remains the main test opportunity. |
| `cfg/render` | A- | 91.9% | Generated output and reporting are well covered with focused modules. |
| `cfg/pyinfra` | B+ | 88.7% | The process boundary is typed and tested; platform/error branches account for most misses. |
| `cfg/host` and `cfg/deploys` | C+ | 75.7% / 72.2% | Core host logic is healthy, but pyinfra deploy operations are expensive to exercise and remain the weakest area. |

Repository-wide combined line and branch coverage is 87.7%. The enforced floor
is 87, rounded down from the measured baseline so the gate never claims more
than the suite proves. Ruff enforces cyclomatic complexity at 15, mypy runs in
strict mode for `cfg/`, beartype checks package call boundaries at runtime, and
the full test suite runs in parallel with timeouts.

## Maintenance

- Do not lower the coverage floor. Raise it when the measured baseline crosses
  the next integer.
- Update this table after a material package split, a quality-gate change, or a
  concentrated test campaign—not for every small patch.
- Treat a failing type, dependency, dead-code, architecture, or test hook as a
  product defect unless a narrow documented exemption reflects intentional
  behavior.
- Revisit `docs/architecture.md` and this scorecard a couple of times a year.
