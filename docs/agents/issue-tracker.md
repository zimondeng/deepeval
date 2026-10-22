# Issue tracker: GitHub

Issues and specs for this repo live as GitHub Issues in `zimondeng/deepeval`. Use the `gh` CLI for all issue operations.

## Conventions

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --json number,title,body,labels,comments`
- List: `gh issue list --state open --json number,title,body,labels,comments`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."`
- Close: `gh issue close <number> --comment "..."`

PRs are not treated as a triage request surface.

Task graphs should use GitHub sub-issues and native issue dependencies where supported. When unsupported, record `Part of #<parent>` and `Blocked by: #<issue>` in issue bodies.
