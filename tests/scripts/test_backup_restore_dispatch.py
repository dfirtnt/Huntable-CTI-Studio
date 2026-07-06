from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_backup_restore_python_dispatch_targets_exist():
    script_path = PROJECT_ROOT / "scripts" / "backup_restore.sh"
    script_text = script_path.read_text()

    referenced_scripts = set()
    for line in script_text.splitlines():
        line = line.strip()
        if not line.startswith("python3 scripts/"):
            continue
        script_ref = line.split()[1]
        referenced_scripts.add(PROJECT_ROOT / script_ref)

    assert referenced_scripts
    missing_scripts = [path for path in sorted(referenced_scripts) if not path.exists()]
    assert missing_scripts == []
