"""End-to-end backup → restore round trip against a real PostgreSQL.

Every other backup test mocks Docker and psql. This one does not: it seeds a
throwaway database, backs it up with the real `backup_database_v3.create_backup`,
verifies the artifact with the real `verify_backup`, and restores it with the
real `restore_system.restore_database` — then compares the two databases.

Safety
------
`restore_system.restore_database` issues DROP DATABASE against whatever
`DB_CONFIG["database"]` names, so this module never lets that be the production
database. Both scratch databases carry a `backup_roundtrip_` prefix and a random
suffix, every create/drop asserts that prefix, and the fixture drops them on the
way out. The production database is only ever read, and only to confirm it is
still there afterwards.

What it does not cover: `backup_system.create_system_backup`'s parallel
component orchestration, and the container stop/start dance in
`restore_database_v2` (which would bounce the operator's running dev stack).
Those stay unit-tested.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_database_v3  # noqa: E402
import backup_system  # noqa: E402
import restore_system  # noqa: E402
import verify_backup  # noqa: E402

CONTAINER = "cti_postgres"
DB_USER = "cti_user"
PRODUCTION_DB = "cti_scraper"
SCRATCH_PREFIX = "backup_roundtrip_"

# Deliberately awkward payload: embedded newlines, a tab, unicode, backslashes,
# and a literal \N — the sequences COPY escaping and the dump filter are most
# likely to mangle.
ARTICLE_CONTENT = (
    "Line one\nLine two\tTabbed\n"
    "Unicode: café 中文 — em dash\n"
    "Backslash path: C:\\Windows\\System32\\cmd.exe\n"
    "Literal null marker: \\N\n"
)


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return CONTAINER in result.stdout


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_available(), reason=f"{CONTAINER} container is not running"),
]


def _psql(database: str, sql: str, *, tuples_only: bool = True) -> str:
    """Run one statement and return stdout. No shell, so no quoting hazards."""
    cmd = ["docker", "exec", CONTAINER, "psql", "-U", DB_USER, "-d", database, "-v", "ON_ERROR_STOP=1"]
    if tuples_only:
        cmd += ["-t", "-A"]
    cmd += ["-c", sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"psql failed on {database}: {result.stderr}"
    return result.stdout.strip()


def _assert_scratch(database: str) -> None:
    assert database.startswith(SCRATCH_PREFIX), f"refusing to touch non-scratch database: {database}"
    assert database != PRODUCTION_DB


def _create_database(database: str) -> None:
    _assert_scratch(database)
    _psql("postgres", f'CREATE DATABASE "{database}";')


def _drop_database(database: str) -> None:
    _assert_scratch(database)
    subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            "postgres",
            "-c",
            f'DROP DATABASE IF EXISTS "{database}";',
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


class ScratchDatabases:
    """Mints uniquely named scratch databases and remembers them for teardown."""

    def __init__(self) -> None:
        self._names: list[str] = []

    def _name(self, role: str) -> str:
        name = f"{SCRATCH_PREFIX}{role}_{uuid.uuid4().hex[:8]}"
        self._names.append(name)
        return name

    def create(self, role: str) -> str:
        name = self._name(role)
        _create_database(name)
        return name

    def reserve(self, role: str) -> str:
        """Reserve a name for a database the code under test will create itself."""
        return self._name(role)

    def cleanup(self) -> None:
        for name in self._names:
            _drop_database(name)


@pytest.fixture
def scratch() -> ScratchDatabases:
    databases = ScratchDatabases()
    try:
        yield databases
    finally:
        databases.cleanup()


def seed_source_database(database: str) -> None:
    """Create a miniature schema carrying the hazards real dumps carry."""
    _psql(
        database,
        """
        CREATE TABLE sources (
            id integer PRIMARY KEY,
            name text NOT NULL,
            url text
        );
        CREATE TABLE articles (
            id integer PRIMARY KEY,
            source_id integer NOT NULL REFERENCES sources(id),
            title text NOT NULL,
            content text,
            published_at timestamptz DEFAULT now()
        );
        CREATE INDEX articles_source_id_idx ON articles (source_id);
        INSERT INTO sources (id, name, url) VALUES
            (1, 'Alpha Intel', 'https://alpha.example/feed'),
            (2, 'Beta Labs', 'https://beta.example/feed'),
            (3, 'Gamma Research', 'https://gamma.example/feed');
        """,
    )
    for article_id, source_id, title in (
        (1, 1, "First report"),
        (2, 1, "Second report"),
        (3, 2, "Third report"),
        (4, 2, "Fourth report"),
        (5, 3, "Orphan candidate"),
    ):
        _psql(
            database,
            f"INSERT INTO articles (id, source_id, title, content) "
            f"VALUES ({article_id}, {source_id}, $t${title}$t$, $c${ARTICLE_CONTENT}$c$);",
        )


def snapshot_shape(database: str) -> dict[str, object]:
    """A comparable fingerprint of a database's user-visible contents."""
    return {
        "tables": _psql(
            database,
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;",
        ).split("\n"),
        "sources": _psql(database, "SELECT count(*) FROM sources;"),
        "articles": _psql(database, "SELECT count(*) FROM articles;"),
        "content_digest": _psql(database, "SELECT md5(string_agg(content, '|' ORDER BY id)) FROM articles;"),
        "title_digest": _psql(database, "SELECT md5(string_agg(title, '|' ORDER BY id)) FROM articles;"),
    }


def make_backup(source_db: str, backup_dir: Path, monkeypatch) -> tuple[Path, dict]:
    """Run the real backup script against the scratch database, then compress.

    Returns the .sql.gz artifact and the system-backup-shaped metadata that
    restore_system and verify_backup both consume.
    """
    monkeypatch.setitem(backup_database_v3.DB_CONFIG, "database", source_db)
    assert backup_database_v3.DB_CONFIG["database"] == source_db

    result = backup_database_v3.create_backup(str(backup_dir))
    assert result["success"] is True, result.get("error")

    raw_dump = Path(result["backup_path"])
    compressed = raw_dump.with_suffix(".sql.gz")
    with open(raw_dump, "rb") as f_in, gzip.open(compressed, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw_dump.unlink()

    metadata = {
        "version": "2.0",
        "backup_name": backup_dir.name,
        "components": {
            "database": {
                "filename": compressed.name,
                "checksum": backup_system.calculate_checksum(compressed),
                "size_mb": compressed.stat().st_size / (1024 * 1024),
            }
        },
    }
    (backup_dir / "metadata.json").write_text(json.dumps(metadata))
    return compressed, metadata


def restore_into(target_db: str, backup_dir: Path, metadata: dict, monkeypatch) -> bool:
    """Point the real restore function at a scratch database and run it."""
    _assert_scratch(target_db)
    monkeypatch.setitem(restore_system.DB_CONFIG, "database", target_db)
    # Belt and braces: the restore below issues DROP DATABASE against this name.
    assert restore_system.DB_CONFIG["database"] == target_db
    _assert_scratch(restore_system.DB_CONFIG["database"])

    return restore_system.restore_database(backup_dir, metadata, create_snapshot=False, force=True)


def test_backup_and_restore_round_trip_preserves_the_database(tmp_path, monkeypatch, scratch):
    source_db = scratch.create("src")
    target_db = scratch.reserve("dst")
    seed_source_database(source_db)
    before = snapshot_shape(source_db)

    backup_dir = tmp_path / "system_backup_20260806_180000"
    backup_dir.mkdir()
    compressed, metadata = make_backup(source_db, backup_dir, monkeypatch)

    # The backup script's own metadata must describe what was actually dumped.
    assert compressed.exists()
    assert compressed.stat().st_size > 0

    # The verifier accepts the artifact the producer just wrote.
    verification = verify_backup.verify_backup(backup_dir.name, backup_dir=str(tmp_path))
    assert verification["overall_valid"] is True, verification
    assert verification["tests"]["checksums"]["files_valid"] == 1

    assert restore_into(target_db, backup_dir, metadata, monkeypatch) is True

    after = snapshot_shape(target_db)
    assert after == before

    # Content fidelity is the point: newlines, tabs, unicode and backslashes
    # must survive pg_dump's COPY encoding and the restore filter untouched.
    restored_content = _psql(target_db, "SELECT content FROM articles WHERE id = 1;")
    assert "café 中文" in restored_content
    assert "C:\\Windows\\System32\\cmd.exe" in restored_content
    assert "\\N" in restored_content

    # The FK survives the trip, installed NOT VALID by the restore filter. New
    # writes are still checked; only pre-existing rows are grandfathered.
    assert _psql(target_db, "SELECT count(*) FROM pg_constraint WHERE conname = 'articles_source_id_fkey';") == "1"
    assert _psql(target_db, "SELECT convalidated FROM pg_constraint WHERE conname = 'articles_source_id_fkey';") == "f"

    # And the production database was never in the blast radius.
    assert _psql("postgres", f"SELECT count(*) FROM pg_database WHERE datname = '{PRODUCTION_DB}';") == "1"


def test_restore_survives_a_dump_with_a_dangling_foreign_key(tmp_path, monkeypatch, scratch):
    """The NOT VALID rewrite, proven against a real server.

    A parent row is removed from the dump to reproduce the production case that
    motivated the rewrite (a queue row pointing at a pruned execution). Without
    it, ADD CONSTRAINT revalidates every row and the whole restore aborts.
    """
    source_db = scratch.create("src")
    target_db = scratch.reserve("orphan")
    seed_source_database(source_db)

    backup_dir = tmp_path / "system_backup_20260806_181500"
    backup_dir.mkdir()
    compressed, metadata = make_backup(source_db, backup_dir, monkeypatch)

    with gzip.open(compressed, "rt") as f_in:
        lines = f_in.readlines()

    # Drop source id 3 from the sources COPY block; article 5 references it.
    doctored = [line for line in lines if not line.startswith("3\tGamma Research")]
    assert len(doctored) == len(lines) - 1, "expected exactly one sources COPY row to be removed"

    with gzip.open(compressed, "wt") as f_out:
        f_out.writelines(doctored)
    metadata["components"]["database"]["checksum"] = backup_system.calculate_checksum(compressed)

    assert restore_into(target_db, backup_dir, metadata, monkeypatch) is True

    # The orphan row loaded, and the constraint is present but unvalidated.
    assert _psql(target_db, "SELECT count(*) FROM sources;") == "2"
    assert _psql(target_db, "SELECT count(*) FROM articles;") == "5"
    assert _psql(target_db, "SELECT source_id FROM articles WHERE id = 5;") == "3"
    assert _psql(target_db, "SELECT convalidated FROM pg_constraint WHERE conname = 'articles_source_id_fkey';") == "f"

    # The grandfathered constraint still guards new writes.
    rejected = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            target_db,
            "-c",
            "INSERT INTO articles (id, source_id, title) VALUES (99, 404, 'should fail');",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert rejected.returncode != 0
    assert "violates foreign key constraint" in rejected.stderr
