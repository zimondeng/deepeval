<!-- agent-spec:generated -->
# TypeScript testing

## Scope

The TypeScript package test script in `typescript/package.json` and `.github/workflows/typescript_test.yml`.

## Rules

### Rule 1: CI runs the Jest suite with npm test

Status: Explicit
Confidence: High

Description:
The TypeScript CI workflow runs npm test in the typescript directory and names that step Run Jest tests.

Evidence:
- `.github/workflows/typescript_test.yml` "name: Run Jest tests"
- `.github/workflows/typescript_test.yml` "run: npm test"

Preferred pattern:
Add tests to the suite `npm test` already runs. Do not invent a second unit-test runner for this package.

Exceptions:
`typescript/package.json` also defines test:e2e scripts that invoke the built CLI. Those are not the Jest step.

Verification:
npm test, from the typescript directory.

## Observations

The workflow does not name a test directory. Do not guess one from this spec.
