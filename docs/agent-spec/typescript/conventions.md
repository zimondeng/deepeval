<!-- agent-spec:generated -->
# TypeScript SDK conventions

## Scope

The package in `typescript/package.json`. Compiler settings are in `typescript/tsconfig.json`. Lint rules are in `typescript/eslint.config.mts`. CI is `.github/workflows/typescript_lint.yml`.

## Rules

### Rule 1: Compile as NodeNext

Status: Explicit
Confidence: High

Description:
The TypeScript package sets its module and moduleResolution compiler options to nodenext

Evidence:
- `typescript/tsconfig.json` "nodenext"

Preferred pattern:
Keep new compiler settings compatible with nodenext. Do not switch this package to a bundler resolver.

Exceptions:
`typescript/tsconfig.json` excludes the inspect UI sources from this config. That UI emit is a separate tsconfig and is not covered by this rule.

Verification:
The package build script runs tsc. See `typescript/package.json`.

### Rule 2: Import SDK source through the @/ alias

Status: Explicit
Confidence: High

Description:
ESLint rejects relative imports under typescript/src. Use the @/ alias, rooted at src/, instead of relative imports. One emit target is exempt because it has no alias rewriting step, so siblings must be imported relatively.

Evidence:
- `typescript/eslint.config.mts` "Use the '@/' alias (rooted at src/) instead of relative imports."
- `typescript/eslint.config.mts` "Emits ESM with no alias rewriting step, so siblings must be imported"

Preferred pattern:
Import with the alias from typescript source. Under the inspect UI tree, keep relative imports with explicit extensions, matching the comment in `typescript/eslint.config.mts`.

Exceptions:
The restricted-import rule is turned off for the inspect UI sources in `typescript/eslint.config.mts`.

Verification:
npm run lint, run from the typescript directory. `.github/workflows/typescript_lint.yml` does that.

### Rule 3: CI lints with ESLint and checks Prettier

Status: Explicit
Confidence: High

Description:
Pull requests that touch the TypeScript package run ESLint, then a Prettier check, from the typescript directory.

Evidence:
- `.github/workflows/typescript_lint.yml` "name: Run ESLint"
- `.github/workflows/typescript_lint.yml` "name: Run Prettier (check)"

Preferred pattern:
Run the package lint script and Prettier before a TypeScript pull request. `typescript/eslint.config.mts` ends with eslint-config-prettier so ESLint does not fight Prettier.

Exceptions:
`typescript/.prettierrc` is an empty object. The check still runs. ESLint ignores `dist/**` and `test/**` in `typescript/eslint.config.mts`.

Verification:
npm run lint, from the typescript directory. The workflow also runs npx prettier --check on src and test TypeScript files.

## Observations

`typescript/tsconfig.json` sets strict to true. That is a JSON setting, not a prose rule, and this spec does not restate it as a separate rule.
