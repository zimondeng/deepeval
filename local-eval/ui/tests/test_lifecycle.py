import pytest

from ui.lifecycle import ActiveTaskError, TaskManager


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.processes = []
        self.stale = []
        self.wait_results = {}
        self.start_error = None

    def start(self, command):
        self.commands.append(tuple(command))
        if self.start_error:
            raise self.start_error
        process = FakeProcess()
        self.processes.append(process)
        return process

    def stop(self, container):
        self.commands.append(("docker", "stop", "--time", "10", container))

    def wait_for_exit(self, container, timeout):
        self.commands.append(("wait", container, str(timeout)))
        return self.wait_results.get(container, True)

    def owned_containers(self):
        return list(self.stale)


def test_start_builds_only_the_fixed_compose_command():
    runner = FakeRunner()
    manager = TaskManager(runner, compose_file="local-eval/compose.yaml")

    task = manager.start()

    assert runner.commands[0] == (
        "docker",
        "compose",
        "-f",
        "local-eval/compose.yaml",
        "-p",
        f"deepeval-task-{task.run_id}",
        "run",
        "--rm",
        "--name",
        f"deepeval-task-{task.run_id}",
        "--label",
        f"deepeval.local.owner={task.run_id}",
        "eval",
        "python",
        "-m",
        "evals.test_jev",
    )


def test_each_task_has_a_unique_container_identity():
    runner = FakeRunner()
    manager = TaskManager(runner, compose_file="compose.yaml")

    first = manager.start()
    manager.finish(first.run_id, 0)
    second = manager.start()

    assert first.run_id != second.run_id
    assert first.container_name != second.container_name


def test_second_active_task_is_rejected():
    manager = TaskManager(FakeRunner(), compose_file="compose.yaml")
    manager.start()

    with pytest.raises(ActiveTaskError):
        manager.start()


def test_cancel_stops_container_and_requires_exit_confirmation():
    runner = FakeRunner()
    manager = TaskManager(runner, compose_file="compose.yaml")
    task = manager.start()

    cancelled = manager.cancel(task.run_id)

    assert cancelled.status == "cancelled"
    assert runner.commands[-2:] == [
        ("docker", "stop", "--time", "10", task.container_name),
        ("wait", task.container_name, "30"),
    ]


def test_cancel_stays_cancelling_when_container_does_not_exit():
    runner = FakeRunner()
    manager = TaskManager(runner, compose_file="compose.yaml")
    task = manager.start()
    runner.wait_results[task.container_name] = False

    cancelling = manager.cancel(task.run_id)

    assert cancelling.status == "cancelling"


def test_startup_cleanup_stops_only_owned_stale_containers():
    runner = FakeRunner()
    runner.stale = ["deepeval-task-old"]
    manager = TaskManager(runner, compose_file="compose.yaml")

    cleaned = manager.cleanup_stale()

    assert cleaned == ["deepeval-task-old"]
    assert runner.commands == [
        ("docker", "stop", "--time", "10", "deepeval-task-old"),
        ("wait", "deepeval-task-old", "30"),
    ]


def test_start_failure_cleans_up_container_before_releasing_task_slot():
    runner = FakeRunner()
    runner.start_error = RuntimeError("compose failed")
    manager = TaskManager(runner, compose_file="compose.yaml")

    with pytest.raises(RuntimeError, match="compose failed"):
        manager.start()

    container = runner.commands[0][9]
    assert runner.commands[1:] == [
        ("docker", "stop", "--time", "10", container),
        ("wait", container, "30"),
    ]
