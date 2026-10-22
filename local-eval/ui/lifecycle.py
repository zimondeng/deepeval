"""Safe lifecycle control for the local evaluation container."""

from __future__ import annotations

import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_RUN_ID = re.compile(r"^[0-9a-f]{12}$")
_OWNER_LABEL = "deepeval.local.owner"


class ActiveTaskError(RuntimeError):
    """Raised when a second evaluation is started."""


class UnknownTaskError(KeyError):
    """Raised when a task ID is not owned by this manager."""


class CommandRunner(Protocol):
    def start(self, command: tuple[str, ...]): ...

    def stop(self, container: str): ...

    def wait_for_exit(self, container: str, timeout: int) -> bool: ...

    def owned_containers(self) -> list[str]: ...


@dataclass
class Task:
    run_id: str
    container_name: str
    status: str = "queued"


class TaskManager:
    """Own one evaluation at a time and never accept a user command."""

    def __init__(self, runner: CommandRunner, compose_file: str):
        self._runner = runner
        self._compose_file = compose_file
        self._tasks: dict[str, Task] = {}
        self._active: str | None = None

    def start(self) -> Task:
        if self._active is not None:
            raise ActiveTaskError("an evaluation is already active")

        run_id = uuid.uuid4().hex[:12]
        if not _RUN_ID.fullmatch(run_id):  # pragma: no cover - UUID invariant
            raise RuntimeError("invalid generated task identity")
        container = f"deepeval-task-{run_id}"
        task = Task(run_id, container)
        self._tasks[run_id] = task
        self._active = run_id
        try:
            self._runner.start(self._command(task))
        except Exception:
            task.status = "failed"
            self._runner.stop(task.container_name)
            self._runner.wait_for_exit(task.container_name, timeout=30)
            self._active = None
            raise
        task.status = "running"
        return task

    def finish(self, run_id: str, exit_code: int) -> Task:
        task = self._task(run_id)
        if task.status in {"cancelled", "completed", "failed"}:
            return task
        task.status = "completed" if exit_code == 0 else "failed"
        if self._active == run_id:
            self._active = None
        return task

    def cancel(self, run_id: str) -> Task:
        task = self._task(run_id)
        if task.status not in {"queued", "running", "cancelling"}:
            return task
        task.status = "cancelling"
        self._runner.stop(task.container_name)
        if self._runner.wait_for_exit(task.container_name, timeout=30):
            task.status = "cancelled"
            if self._active == run_id:
                self._active = None
        return task

    def cleanup_stale(self) -> list[str]:
        cleaned = []
        for container in self._runner.owned_containers():
            self._runner.stop(container)
            if self._runner.wait_for_exit(container, timeout=30):
                cleaned.append(container)
        return cleaned

    def _task(self, run_id: str) -> Task:
        try:
            return self._tasks[run_id]
        except KeyError as exc:
            raise UnknownTaskError(run_id) from exc

    def _command(self, task: Task) -> tuple[str, ...]:
        return (
            "docker",
            "compose",
            "-f",
            self._compose_file,
            "-p",
            task.container_name,
            "run",
            "--rm",
            "--name",
            task.container_name,
            "--label",
            f"{_OWNER_LABEL}={task.run_id}",
            "eval",
            "python",
            "-m",
            "evals.test_jev",
        )


class SubprocessRunner:
    """Docker subprocess adapter used by the UI process."""

    def __init__(self, cwd: Path):
        self._cwd = cwd

    def start(self, command: tuple[str, ...]):
        return subprocess.Popen(command, cwd=self._cwd)

    def stop(self, container: str):
        subprocess.run(
            ("docker", "stop", "--time", "10", container),
            cwd=self._cwd,
            check=False,
        )

    def wait_for_exit(self, container: str, timeout: int) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = subprocess.run(
                (
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Status}}",
                    container,
                ),
                cwd=self._cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 or result.stdout.strip() in {
                "exited",
                "dead",
                "removing",
            }:
                return True
            time.sleep(0.1)
        return False

    def owned_containers(self) -> list[str]:
        result = subprocess.run(
            (
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label={_OWNER_LABEL}",
                "--format",
                "{{.Names}}",
            ),
            cwd=self._cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return [line for line in result.stdout.splitlines() if line]
