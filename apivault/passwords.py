"""Password acquisition helpers.

Order of preference for a single command:
    1. ``--password-file <path>``  (recommended for agents: 0600 file)
    2. ``--password-stdin``        (pipe the password)
    3. ``APIVAULT_PASSWORD`` env   (convenient, documented tradeoff)
    4. interactive ``getpass`` prompt (humans)

All values are returned as ``str``; the caller is responsible for not logging
them and for zeroizing where feasible.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path


class PasswordError(Exception):
    """Raised when a password cannot be obtained."""


def read_password(
    *,
    password_file: str | None = None,
    password_stdin: bool = False,
    prompt: str = "Master password: ",
    confirm: bool = False,
) -> str:
    """Obtain a master password using the documented precedence order."""
    if password_file:
        path = Path(password_file).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PasswordError(f"cannot read password file {path}: {exc}") from exc
        if not value:
            raise PasswordError(f"password file {path} is empty")
        return value

    if password_stdin:
        value = sys.stdin.readline().rstrip("\r\n")
        if not value:
            raise PasswordError("no password provided on stdin")
        return value

    env = os.environ.get("APIVAULT_PASSWORD")
    if env:
        return env

    if not sys.stdin.isatty():
        raise PasswordError(
            "no password available: set APIVAULT_PASSWORD, use --password-file, "
            "or run from an interactive terminal"
        )

    pw = getpass.getpass(prompt)
    if confirm:
        pw2 = getpass.getpass("Confirm master password: ")
        if pw != pw2:
            raise PasswordError("passwords do not match")
    if not pw:
        raise PasswordError("empty password is not allowed")
    return pw
