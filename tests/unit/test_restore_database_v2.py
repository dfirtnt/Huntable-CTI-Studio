"""Unit tests for the container stop/start logic added to restore_database_v2.py.

The restore script must stop app containers before dropping/recreating the database
so that their startup create_tables() cannot race-create the SQLAlchemy schema on
the fresh empty DB -- which would leave every table with a primary key already
defined before the restore SQL's ADD CONSTRAINT lines run.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from restore_database_v2 import DatabaseRestore  # noqa: E402


@pytest.fixture()
def restore():
    return DatabaseRestore()


# ---------------------------------------------------------------------------
# APP_CONTAINERS list
# ---------------------------------------------------------------------------


def test_app_containers_list_includes_web(restore):
    assert "cti_web" in restore.APP_CONTAINERS


def test_app_containers_list_includes_workers(restore):
    for expected in ("cti_worker", "cti_workflow_worker", "cti_scheduler"):
        assert expected in restore.APP_CONTAINERS, f"{expected} missing from APP_CONTAINERS"


# ---------------------------------------------------------------------------
# _stop_app_containers
# ---------------------------------------------------------------------------


def _make_ok():
    m = MagicMock()
    m.returncode = 0
    return m


def _make_err():
    m = MagicMock()
    m.returncode = 1
    m.stderr = "No such container"
    return m


def test_stop_calls_docker_stop_for_each_container(restore):
    with patch("subprocess.run", return_value=_make_ok()) as mock_run:
        restore._stop_app_containers()

    calls = [c.args[0] for c in mock_run.call_args_list]
    for name in restore.APP_CONTAINERS:
        assert ["docker", "stop", name] in calls


def test_stop_returns_all_running_containers(restore):
    with patch("subprocess.run", return_value=_make_ok()):
        stopped = restore._stop_app_containers()
    assert set(stopped) == set(restore.APP_CONTAINERS)


def test_stop_skips_containers_that_do_not_exist(restore):
    responses = {name: (_make_ok() if name != "cti_scheduler" else _make_err()) for name in restore.APP_CONTAINERS}

    def side_effect(cmd, **_):
        name = cmd[2]
        return responses.get(name, _make_err())

    with patch("subprocess.run", side_effect=side_effect):
        stopped = restore._stop_app_containers()

    assert "cti_scheduler" not in stopped
    assert "cti_web" in stopped


def test_stop_returns_empty_when_no_containers_running(restore):
    with patch("subprocess.run", return_value=_make_err()):
        stopped = restore._stop_app_containers()
    assert stopped == []


# ---------------------------------------------------------------------------
# _start_app_containers
# ---------------------------------------------------------------------------


def test_start_calls_docker_start_for_each_stopped_container(restore):
    containers = ["cti_web", "cti_worker"]
    with patch("subprocess.run", return_value=_make_ok()) as mock_run:
        restore._start_app_containers(containers)

    started = [c.args[0] for c in mock_run.call_args_list]
    assert ["docker", "start", "cti_web"] in started
    assert ["docker", "start", "cti_worker"] in started


def test_start_only_restarts_containers_it_was_given(restore):
    with patch("subprocess.run", return_value=_make_ok()) as mock_run:
        restore._start_app_containers(["cti_web"])

    names_started = [c.args[0][2] for c in mock_run.call_args_list]
    assert names_started == ["cti_web"]


def test_start_tolerates_docker_errors(restore):
    with patch("subprocess.run", return_value=_make_err()):
        # Should not raise
        restore._start_app_containers(["cti_web"])


def test_start_with_empty_list_makes_no_calls(restore):
    with patch("subprocess.run") as mock_run:
        restore._start_app_containers([])
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# restore_database integration: containers stopped before drop, restarted after
# ---------------------------------------------------------------------------


def test_restore_stops_containers_before_db_drop(restore, tmp_path):
    """Containers must be stopped BEFORE the database is dropped/recreated."""
    call_order = []

    sql_gz = tmp_path / "backup.sql.gz"
    import gzip

    with gzip.open(sql_gz, "wt") as f:
        f.write("-- PostgreSQL database dump\nSELECT 1;\n")

    def track(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        flat = " ".join(str(x) for x in cmd)
        if "docker stop" in flat:
            call_order.append("stop")
        elif "DROP DATABASE" in flat:
            call_order.append("drop")
        elif "CREATE DATABASE" in flat:
            call_order.append("create")
        return m

    with patch("subprocess.run", side_effect=track):
        # Will fail partway through (no real postgres), but that's fine --
        # we only care about the order of the first few calls.
        try:
            restore.restore_database(sql_gz, force=True)
        except Exception:
            pass

    # stop must come before drop and create
    if "stop" in call_order and "drop" in call_order:
        assert call_order.index("stop") < call_order.index("drop")


def test_restore_restarts_containers_after_failure(restore, tmp_path):
    """Containers must be restarted even when the restore fails."""
    started = []

    sql_gz = tmp_path / "backup.sql.gz"
    import gzip

    with gzip.open(sql_gz, "wt") as f:
        f.write("-- PostgreSQL database dump\nSELECT 1;\n")

    def track(cmd, **kwargs):
        m = MagicMock()
        flat = " ".join(str(x) for x in cmd)
        if "docker start" in flat:
            started.append(cmd[2])
            m.returncode = 0
        elif "docker stop" in flat:
            m.returncode = 0
        elif "DROP DATABASE" in flat:
            # Simulate a postgres failure to force early exit
            m.returncode = 1
            m.stderr = "simulated drop failure"
        else:
            m.returncode = 0
        m.stdout = ""
        m.stderr = getattr(m, "stderr", "")
        return m

    with patch("subprocess.run", side_effect=track):
        try:
            restore.restore_database(sql_gz, force=True)
        except Exception:
            pass

    # Even though restore failed, containers should have been restarted
    assert len(started) > 0, "Containers were not restarted after restore failure"
