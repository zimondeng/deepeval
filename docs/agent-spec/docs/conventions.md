<!-- agent-spec:generated -->
# Docs site conventions

## Scope

The Next.js docs site in `docs/package.json`. Collection config is `docs/source.config.ts`. Docs pages live under the content tree, with sidebar metadata in `docs/content/docs/meta.json`.

## Rules

### Rule 1: Docs and integrations pages must declare languages

Status: Explicit
Confidence: High

Description:
languages is required for docs and integrations because those are the reference surfaces the language selector acts on. An undeclared page there would follow whatever the reader last picked.

Evidence:
- `docs/source.config.ts` "`languages` is required for docs and integrations because those are the"
- `docs/source.config.ts` "reference surfaces the language selector acts on"

Preferred pattern:
Set languages on every new page in the docs and integrations collections. Guides, tutorials, changelog, and blog stay optional, as the comment in `docs/source.config.ts` says.

Exceptions:
none found

Verification:
npm run types:check, from the docs directory. That script runs fumadocs-mdx.

### Rule 2: beta is only the literal true, or omitted

Status: Explicit
Confidence: High

Description:
beta true marks a page as beta. Omission means not-beta. Do not write beta false. The schema only accepts the literal true, so an explicit false fails the build.

Evidence:
- `docs/source.config.ts` "`beta: true` marks a page as beta"
- `docs/source.config.ts` "not-beta — do not write `beta: false`; the schema only accepts the literal"
- `docs/source.config.ts` "`true`, so an explicit false fails the build."

Preferred pattern:
Add beta only as true. Leave the field out when the page is not beta.

Exceptions:
none found

Verification:
npm run types:check, from the docs directory.

### Rule 3: peek is only the literal true, or omitted

Status: Explicit
Confidence: High

Description:
peek true hides a mascot behind the page title. Like beta, omit it rather than writing peek false.

Evidence:
- `docs/source.config.ts` "`peek: true` hides a mascot behind the page title that peeks over it now"
- `docs/source.config.ts` "omit it rather than writing `peek: false`."

Preferred pattern:
Add peek only as true. Otherwise omit it.

Exceptions:
none found

Verification:
npm run types:check, from the docs directory.

## Observations

`DOCS.md` at the repository root is a branch note about voice docs sections. It is not a standing authoring rule.
