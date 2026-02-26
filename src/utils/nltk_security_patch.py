"""
Runtime patch for NLTK CVE-2025-14009 (Zip Slip / RCE in downloader).

Replaces nltk.downloader._unzip_iter with a secure implementation that:
- Validates extraction paths to prevent Zip-Slip (.., absolute paths).
- Prevents writes through pre-existing symlinks that escape the root.
- Uses per-member extraction instead of extractall().

No-op if nltk is not installed. Apply by importing this module at app startup.
"""

from __future__ import annotations

import os
import sys
import zipfile


def _secure_unzip_iter(filename: str, root: str, verbose: bool = True):
    """
    Secure ZIP extraction: prevents Zip-Slip and symlink-escape.
    Yields ErrorMessage on validation failure; otherwise same behaviour as original.
    """
    if verbose:
        sys.stdout.write(f"Unzipping {os.path.split(filename)[1]}")
        sys.stdout.flush()

    try:
        zf = zipfile.ZipFile(filename)
    except zipfile.BadZipFile:
        from nltk.downloader import ErrorMessage

        yield ErrorMessage(filename, "Error with downloaded zip file")
        return
    except Exception as e:
        from nltk.downloader import ErrorMessage

        yield ErrorMessage(filename, e)
        return

    from nltk.downloader import ErrorMessage

    root_abs = os.path.abspath(root)
    root_real = os.path.realpath(root_abs)
    root_prefix = root_real.rstrip(os.sep) + os.sep
    os.makedirs(root, exist_ok=True)

    try:
        for member in zf.namelist():
            raw_target = os.path.join(root_abs, member)
            target_abs = os.path.abspath(raw_target)

            if not target_abs.startswith(root_prefix):
                yield ErrorMessage(filename, f"Zip Slip blocked: {member}")
                continue

            try:
                target_real = os.path.realpath(target_abs)
            except OSError:
                target_real = target_abs
            if not target_real.startswith(root_prefix):
                yield ErrorMessage(filename, f"Symlink escape blocked: {member}")
                continue

            try:
                zf.extract(member, root)
            except Exception as e:
                yield ErrorMessage(filename, f"Extraction error for {member}: {e}")
    finally:
        zf.close()

    if verbose:
        print()


def apply_nltk_security_patch() -> bool:
    """Patch nltk.downloader._unzip_iter if nltk is installed. Return True if patched."""
    try:
        import nltk.downloader as downloader_mod

        downloader_mod._unzip_iter = _secure_unzip_iter
        return True
    except ImportError:
        return False


# Apply on import so any entry point that imports this module gets the patch.
apply_nltk_security_patch()
