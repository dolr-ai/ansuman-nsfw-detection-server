import shutil
from pathlib import Path


def cleanup_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)

