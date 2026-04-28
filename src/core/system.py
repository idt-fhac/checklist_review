from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import subprocess
import sys


@dataclass
class FolderSelection:
    path: str
    collection_name: str


class FolderSelectionError(RuntimeError):
    pass


def _choose_directory_macos() -> str:
    script = 'set theFolder to choose folder with prompt "Select a PDF folder"\nPOSIX path of theFolder'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FolderSelectionError(result.stderr.strip() or "Folder selection cancelled.")
    path = result.stdout.strip()
    if not path:
        raise FolderSelectionError("Folder selection cancelled.")
    return path


def _choose_directory_tk_subprocess() -> str:
    script = """
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.update()
path = filedialog.askdirectory(title="Select a PDF folder")
root.destroy()
if not path:
    raise SystemExit(1)
print(path)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FolderSelectionError("Folder selection cancelled.")
    path = result.stdout.strip()
    if not path:
        raise FolderSelectionError("Folder selection cancelled.")
    return path


def choose_directory() -> FolderSelection:
    try:
        if platform.system() == "Darwin":
            selected_path = _choose_directory_macos()
        else:
            selected_path = _choose_directory_tk_subprocess()
    except FileNotFoundError as exc:
        raise FolderSelectionError("Folder picker utility not available on this system.") from exc
    except Exception as exc:
        raise FolderSelectionError(str(exc)) from exc

    expanded_path = str(Path(selected_path).expanduser())
    collection_name = Path(expanded_path).name or Path(expanded_path).stem or "untitled"
    return FolderSelection(path=expanded_path, collection_name=collection_name)
