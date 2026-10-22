# A4 credential-boundary experiment

Date: 2026-10-22

## Setup

This experiment uses only these fake values:

- Jev key: `fake-jev-secret`
- target header value: `fake-target-secret`
- proxy URL: `http://proxy-user:fake-proxy-secret@proxy.test:8080`

The child process is a Python fixture. It does not contact Jev, a target
service, or a proxy. The harness records the child command, environment,
stdin, and files created below a fresh temporary directory.

## Candidates

| Candidate | Command args | Child environment | Files | Result |
|---|---|---|---|---|
| environment injection | no secret in args | contains fake values | none | rejected: process/container metadata can expose environment |
| temporary credential file | path in args | no secret | contains fake values | rejected: mount/file persists beyond the read and is exportable |
| stdin envelope | no secret in args | no fake values | none | selected: child reads one JSON envelope and closes stdin |

The selected mechanism is implemented by `CredentialEnvelope.to_stdin()` and
`SubprocessRunner.start()`. The evaluator receives the envelope once over
stdin; Jev, target, and proxy adapters keep the values in process memory.

## Redaction checks

With redaction enabled, the fake Jev key, target header value, and proxy URL
are absent from error text, console report text, JSON report output, and any
serialized browser-export payload. Configuration export contains only the
Jev credential reference and rejects credential-bearing target headers and
credential-bearing URLs.

The browser boundary has no credential storage implementation: credentials
must remain in page memory and are not written to `localStorage`,
`sessionStorage`, IndexedDB, downloads, or browser export data. The evaluator
creates no credential temporary file.

## Limits

This is an isolated fake-process experiment, not a Docker daemon or real Jev
verification. Docker/container inspection, administrator access, Python
memory inspection, OS swap, and crash dumps remain outside the guarantee.
Python cannot reliably erase immutable string objects after the session ends.
The existing CLI `.env` workflow remains intentionally compatible and is not
covered by the UI session guarantee. A real deployment must still verify that
its browser code and Docker runtime preserve these boundaries.
