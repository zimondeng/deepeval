<!-- agent-spec:generated -->
# Project engineering specifications

Read only the specifications that match the files you will change. Date: 2026-10-21.

This repository holds four packages: the Python library at the root, the TypeScript SDK in `typescript/package.json`, the docs site in `docs/package.json`, and the setup wizard in `setup-wizard/package.json`.

## Specification index

| Scope | Read |
|---|---|
| Pull request titles | [conventions.md](conventions.md) |
| Python formatting, Poetry, Ruff, telemetry mypy | [python/conventions.md](python/conventions.md) |
| Python package boundaries and metric shape | [python/architecture.md](python/architecture.md) |
| Python tests | [python/testing.md](python/testing.md) |
| TypeScript SDK style and lint | [typescript/conventions.md](typescript/conventions.md) |
| TypeScript tests | [typescript/testing.md](typescript/testing.md) |
| Setup wizard | [setup-wizard/conventions.md](setup-wizard/conventions.md) |
| Docs site frontmatter | [docs/conventions.md](docs/conventions.md) |

When editing the setup wizard, also read `setup-wizard/AGENTS.md`. That file is the long-form source. The spec records the rules a change must not break.

## Priority

Explicit rules win over Observed rules. If either disagrees with the code, stop and check which one is outdated. There is no proposals file. Do not treat observations as binding rules.
