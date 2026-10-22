# Compose UI feasibility experiment

Date: 2026-10-22

## Host checks

- `docker version`: passed with Docker Desktop 4.90.0, Linux engine.
- `docker compose version`: passed with Compose v5.5.1.
- `docker compose ... run --rm eval docker --version`: failed as expected with
  `exec: "docker": executable file not found in $PATH`.

## Result

The existing evaluation image cannot run the proposed sibling-container UI service:
its Dockerfile does not install the Docker CLI or Compose plugin. Adding daemon
socket access alone would therefore not provide a control path.

The current Compose file also uses relative bind mounts (`./evals`, `./datasets`,
and `./reports`). If the UI runs inside a Linux container, those paths resolve
from the UI container's filesystem while the Docker Desktop daemon creates the
sibling container elsewhere. The UI cannot safely assume its `/eval` path is a
Windows host path. Passing an arbitrary host path from an HTTP request would
violate the path and command boundary in the system specification.

This ticket keeps the lifecycle boundary dependency-injected and fixed-command,
so a host-process runner can be used without changing task semantics. A Compose
UI deployment remains blocked until a controlled host-path/daemon transport is
validated (or the UI is deliberately run as a host process). No Docker socket,
host path, or credential mount was added based on an unverified assumption.
