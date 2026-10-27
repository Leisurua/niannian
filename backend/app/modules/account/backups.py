"""Retention for explicitly managed, timestamp-named backup files only."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

NAME = re.compile(r'niannian-backup-(\d{8}T\d{6}Z)\.(?:dump|sql.gz|tar.gz|zip)')


def prune(directory, days, *, apply=False, now=None):
    """Never walk recursively, follow links, or delete unrelated filenames.

    The timestamp is the backup's UTC snapshot time, not its last copy/mtime.
    This enforces only this directory's policy, not cloud/offsite snapshots.
    """
    if not 1 <= days <= 365:
        raise ValueError('Retention must be between 1 and 365 days')
    source = Path(directory)
    if source.is_symlink() or source.is_junction():
        raise ValueError('Backup directory cannot be a link')
    root = source.resolve(strict=True)
    if not root.is_dir() or root.parent == root:
        raise ValueError('An explicit backup directory is required')
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    removed = []
    for path in sorted(root.iterdir()):
        match = NAME.fullmatch(path.name)
        if not match:
            continue
        if path.is_symlink() or path.is_junction() or not path.is_file() or path.resolve().parent != root:
            raise ValueError('Refusing a linked or non-file backup')
        snapshot_at = datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if snapshot_at <= cutoff:
            if apply:
                path.unlink()
            removed.append(path.name)
    return removed
