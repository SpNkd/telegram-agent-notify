#!/usr/bin/env python3
"""Install the notifier and optional agent skills without third-party packages."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Iterable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ask(question: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    answer = input(question + suffix + " ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def copy_tree(source: Path, destination: Path, force: bool) -> None:
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative = source_file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            print(f"skip (exists): {target}")
            continue
        shutil.copy2(source_file, target)


def write_launcher(path: Path, application: Path, windows: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if windows:
        content = f'@echo off\r\npy -3 "{application}" %*\r\n'
    else:
        python = '"${PYTHON:-python3}"'
        # shlex.quote is deliberately avoided here: this is a fixed single-quoted
        # literal in a generated launcher, not user-provided shell input.
        escaped_application = str(application).replace("'", "'\\''")
        content = f"#!/bin/sh\nset -eu\nexec {python} '{escaped_application}' \"$@\"\n"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    if not windows:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install(args: argparse.Namespace) -> int:
    windows = os.name == "nt"
    if args.prefix:
        prefix = Path(args.prefix).expanduser().resolve()
        application_dir = prefix / ("telegram-agent-notify" if windows else "share/telegram-agent-notify")
        binary_dir = prefix / ("telegram-agent-notify" if windows else "bin")
        codex_root = prefix / ".agents" / "skills"
        claude_root = prefix / ".claude" / "skills"
    else:
        if windows:
            data_root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home() / "AppData" / "Local")
            application_dir = data_root / "telegram-agent-notify"
            binary_dir = application_dir
            codex_root = Path(os.environ.get("USERPROFILE") or Path.home()) / ".agents" / "skills"
            claude_root = Path(os.environ.get("USERPROFILE") or Path.home()) / ".claude" / "skills"
        else:
            data_root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
            application_dir = data_root / "telegram-agent-notify"
            binary_dir = Path(args.bin_dir).expanduser() if args.bin_dir else Path.home() / ".local" / "bin"
            codex_root = Path.home() / ".agents" / "skills"
            claude_root = Path.home() / ".claude" / "skills"

    application_dir.mkdir(parents=True, exist_ok=True)
    core_source = PROJECT_ROOT / "src" / "telegram_notify.py"
    core_target = application_dir / "telegram_notify.py"
    if not core_target.exists() or args.force:
        shutil.copy2(core_source, core_target)
    launcher_name = "telegram-notify.cmd" if windows else "telegram-notify"
    write_launcher(binary_dir / launcher_name, core_target, windows)
    print(f"Installed CLI: {binary_dir / launcher_name}")

    install_codex = args.codex if args.codex is not None else (ask("Install the Codex skill?") if not args.yes else True)
    install_claude = args.claude if args.claude is not None else (ask("Install the Claude Code skill?") if not args.yes else True)
    if install_codex:
        copy_tree(PROJECT_ROOT / "skills" / "codex", codex_root / "telegram-notify", args.force)
        print(f"Installed Codex skill: {codex_root / 'telegram-notify'}")
    if install_claude:
        copy_tree(PROJECT_ROOT / "skills" / "claude", claude_root / "telegram-notify", args.force)
        print(f"Installed Claude Code skill: {claude_root / 'telegram-notify'}")
    print("Next step: telegram-notify configure")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Install telegram-agent-notify for the current user.")
    parser.add_argument("--prefix", type=Path, help="use an isolated installation root (useful for testing)")
    parser.add_argument("--bin-dir", type=Path, help="override the Unix launcher directory")
    parser.add_argument("--codex", dest="codex", action="store_true", help="install only the Codex skill")
    parser.add_argument("--no-codex", dest="codex", action="store_false", help="skip the Codex skill")
    parser.add_argument("--claude", dest="claude", action="store_true", help="install only the Claude Code skill")
    parser.add_argument("--no-claude", dest="claude", action="store_false", help="skip the Claude Code skill")
    parser.add_argument("--yes", action="store_true", help="accept default skill choices")
    parser.add_argument("--force", action="store_true", help="overwrite installed files")
    parser.set_defaults(codex=None, claude=None)
    return install(parser.parse_args(list(argv) if argv is not None else None))


if __name__ == "__main__":
    raise SystemExit(main())
