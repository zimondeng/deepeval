<!-- agent-spec:generated -->
# Repository conventions

## Scope

Pull requests to this repository. The checker is `.github/workflows/pr-title-check.yml`.

## Rules

### Rule 1: Pull request titles use the semantic types the workflow lists

Status: Explicit
Confidence: High

Description:
The pull request title check allows feat, fix, docs, refactor, chore, test, perf, ci, and build. It runs `action-semantic-pull-request` on opened, edited, synchronize, and reopened pull requests.

Evidence:
- `.github/workflows/pr-title-check.yml` "name: PR title check"
- `.github/workflows/pr-title-check.yml` "uses: amannn/action-semantic-pull-request@v5"
- `.github/workflows/pr-title-check.yml` "feat fix docs refactor chore test perf ci build"

Preferred pattern:
Use one of those types as the title prefix.

Exceptions:
none found

Verification:
The workflow runs on pull requests. No local command is specified.

## Observations

none
