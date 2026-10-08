# ADR-0014: Compositions are Go templates

- **Status:** Accepted. Supersedes §3 of [ADR-0006](0006-database-api-and-python-compositions.md)
- **Date:** 2026-10-07
- **Phase:** between v5-agentic and v6-proof

## Context

From v2 to v5, both platform APIs were composed by Python running on
`function-python`. The logic lived in `compose.py` with pytest unit tests,
and a generator embedded it into each Composition (ADR-0006 §3).

It worked, but it put an unusual skill at the centre of the platform:

- **Reviewers had to read Python to review infrastructure.** A change to what
  "small" means was a diff to a dict in a script, embedded by a generator,
  inside a YAML block scalar.
- **Templating is what the team already knows.** Helm charts are everywhere at
  Fernhill (story, problem #2), and Go templates with Sprig are the shared
  language between the platform team and the stream-aligned teams.
- **Two artifacts for one thing.** `compose.py` was the source and
  `composition.yaml` was generated from it, so a drift check was needed just to
  keep them equal.

## Decision

**Compositions use `function-go-templating` (v0.13.0), with the template
inline in `composition.yaml`. The Composition is the single source of truth.**

- The output reads like the Kubernetes objects it produces. Size tables are
  Sprig `dict`s at the top of each template, where reviewers expect "config" to live.
- Readiness uses the function's `getResourceCondition`, which returns
  `Unknown` for not-yet-observed resources, so there are no nil checks.
- XR status is written by emitting the XR's own kind without a resource-name
  annotation, the function's documented convention.
- **Tests render real XRs through the real Composition** with
  `crossplane render`, including simulated observed state for readiness
  (`platform/apis/tests/`). Every assertion from the old Python unit tests was
  ported, and a negative control (changing a size) makes them fail.

The tenant-facing APIs (XRDs) **did not change**. No tenant file, golden path,
MCP tool, or policy changed. Swapping the composition engine underneath the
API is the abstraction doing its job (ADR-0006 §1).

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Keep `function-python` | Testable, but optimises for the language of whoever wrote it, not for the people who review and operate it. |
| KCL (`function-kcl`) | Typed and expressive. Another language to learn; the team already has Go templates from Helm. |
| Patch-and-transform | Too limited for conditional resources (PDB, route) and readiness logic; it reads as pages of patches. |
| Templates in separate `.tmpl` files (`source: FileSystem`) | Needs the files mounted into the function's pod. Inline keeps the Composition self-contained and diffable in one place. |

## Consequences

- **Reviewers review one file**, in the same idiom as the Helm charts they already read.
- **Tests are slower but more honest.** About a minute per suite, because each
  case runs the function container (Docker required), versus milliseconds for
  pure Python. They now test the exact artifact the cluster runs, instead of a
  function that a generator then embedded.
- **Logic is harder to express.** Go templates are weak at data manipulation.
  If a composition ever needs real computation (cross-resource lookups,
  non-trivial validation), add a pipeline step in another function for that
  piece rather than contort the template.
- `scripts/gen-compositions.py` became `scripts/gen-catalog.py`. It now only
  embeds XRDs into the portal's API entities (ADR-0011).
- The `v2`–`v5` tags still show the Python implementation. The history is
  part of the story: the API outlived its first implementation.

## What would change my mind

- Templates start needing helpers or copy-paste between APIs. Then move shared
  pieces into a packaged function, or into `function-go-templating`'s
  `FileSystem` source with shared partials.
- Test time becomes a bottleneck. Then cache the function image in CI and
  render cases in parallel before reconsidering the engine.
