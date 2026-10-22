<!-- agent-spec:generated -->
# Setup wizard conventions

## Scope

The `setup-wizard/package.json` package. The long-form source is `setup-wizard/AGENTS.md`. Follow that file when this spec and the guide both speak. This file records the constraints a change must not break.

## Rules

### Rule 1: The wizard creates evaluations, not tracing setup

Status: Explicit
Confidence: High

Description:
Keep the wizard focused on creating and running evaluations, not general tracing setup.

Evidence:
- `setup-wizard/AGENTS.md` "Keep it focused on creating and running evaluations, not general tracing setup."

Preferred pattern:
Do not add general tracing setup to this package.

Exceptions:
none found

Verification:
npm run check, from the setup-wizard directory. `.github/workflows/setup_wizard_test.yml` runs that.

### Rule 2: The check script is format, lint, typecheck, and test

Status: Explicit
Confidence: High

Description:
The package check script runs format:check, lint, typecheck, and npm test. CI runs npm run check.

Evidence:
- `setup-wizard/package.json` "npm run format:check && npm run lint && npm run typecheck && npm test"
- `.github/workflows/setup_wizard_test.yml` "run: npm run check"

Preferred pattern:
Run npm run check before handing the wizard change over.

Exceptions:
none found

Verification:
npm run check

### Rule 3: Never put an API key or setup token in logs or telemetry

Status: Explicit
Confidence: High

Description:
Never log, serialize, pass as an argument, or send telemetry containing an API key or setup token.

Evidence:
- `setup-wizard/AGENTS.md` "Never log, serialize, pass as an argument, or send telemetry containing an API key or setup token."

Preferred pattern:
Keep keys out of logs, function arguments that get serialized, and telemetry payloads.

Exceptions:
none found

Verification:
npm test

### Rule 4: Confident AI is opt-in, and the local path makes no Confident calls

Status: Explicit
Confidence: High

Description:
Using Confident AI is always an explicit opt-in. The local choice stays a first-class path that makes no Confident AI calls.

Evidence:
- `setup-wizard/AGENTS.md` "Using Confident AI is always an explicit opt-in, and"
- `setup-wizard/AGENTS.md` "stays a first-class path that makes no Confident AI calls."

Preferred pattern:
Do not call Confident AI on the local path. Do not make opt-in the default.

Exceptions:
none found

Verification:
npm test

### Rule 5: Unit tests must not use the network

Status: Explicit
Confidence: High

Description:
Network behavior must be mockable. Unit tests must not access the network.

Evidence:
- `setup-wizard/AGENTS.md` "Network behavior must be mockable; unit tests must not access the network."

Preferred pattern:
Inject network access so tests can mock it.

Exceptions:
none found

Verification:
npm test

### Rule 6: Full-permission agent execution needs its own confirmation

Status: Explicit
Confidence: High

Description:
Full-permission agent execution must always follow a separate explicit user confirmation.

Evidence:
- `setup-wizard/AGENTS.md` "Full-permission agent execution must always follow a separate explicit user confirmation."

Preferred pattern:
Do not fold that confirmation into another prompt.

Exceptions:
none found

Verification:
not specified

### Rule 7: One canonical evaluation prompt, component-level, run once

Status: Explicit
Confidence: High

Description:
prompts/evaluation.md is the canonical agent prompt. Avoid duplicate prompt copies. Component-level evaluation is the required shape, and the evaluation runs exactly once.

Evidence:
- `setup-wizard/AGENTS.md` "is the canonical agent prompt. Avoid duplicate prompt"
- `setup-wizard/AGENTS.md` "component-level evaluation is the required shape, with metrics attached to the spans they judge and any end-to-end metric inside that same suite, and the evaluation runs exactly once"

Preferred pattern:
Edit `setup-wizard/prompts/evaluation.md` instead of copying the prompt. Keep component-level evaluation and a single run.

Exceptions:
`setup-wizard/AGENTS.md` describes one black-box path for an application whose language neither SDK covers. Read that section before changing it. This spec does not restate the rest of the prompt policy.

Verification:
not specified

### Rule 8: Do not install into a machine-managed interpreter

Status: Explicit
Confidence: High

Description:
Never install into an interpreter the machine manages. Prefer an existing environment.

Evidence:
- `setup-wizard/AGENTS.md` "Never install into an interpreter the machine manages: prefer an existing"

Preferred pattern:
Prefer an existing environment, otherwise a new project virtualenv. Check install commands against the package manager instead of memory. The guide names the module that decides this.

Exceptions:
none found

Verification:
not specified

### Rule 9: Terminal color goes through the theme module

Status: Explicit
Confidence: High

Description:
Terminal color must go through the theme module. The guide says that module honors NO_COLOR and non-TTY output.

Evidence:
- `setup-wizard/AGENTS.md` "Terminal color must go through"

Preferred pattern:
Do not hard-code colors in wizard UI. Read `setup-wizard/AGENTS.md` for the accent colors and for where log and spinner are imported.

Exceptions:
none found

Verification:
not specified

### Rule 10: Do not commit or push unless the user asks

Status: Explicit
Confidence: High

Description:
Do not commit or push unless the user explicitly asks.

Evidence:
- `setup-wizard/AGENTS.md` "Do not commit or push unless the user explicitly asks."

Preferred pattern:
Leave git commit and git push to an explicit user request.

Exceptions:
none found

Verification:
not specified

## Observations

`setup-wizard/AGENTS.md` also constrains dataset size, metric counts, judge spend, multi-turn detection, and release archive names. Those sentences are binding because they are in that guide. They are not copied here. Read the guide before changing `setup-wizard/prompts/evaluation.md`, `setup-wizard/src/result.ts`, or `setup-wizard/src/judge.ts`.
