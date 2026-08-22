"""Icon and sleep-inhibit — the same two macOS niceties the sender has,
factored out so both apps read from one place.
"""
from __future__ import annotations

import os
import pathlib
import platform
import subprocess

import pygame

ICON = pathlib.Path(__file__).with_name("icon.png")


def set_icon() -> None:
    """The project's own icon, so sender and receiver look like one product.

    set_icon covers Windows and Linux; macOS takes the Cmd-Tab and Dock icon
    from the application, so it also goes to NSApplication via pyobjc — whose
    absence costs the Dock icon and nothing else.
    """
    if not ICON.exists():
        return
    try:
        pygame.display.set_icon(pygame.image.load(str(ICON)))
    except pygame.error:
        return
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication, NSImage
        image = NSImage.alloc().initWithContentsOfFile_(str(ICON))
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        pass


class KeepAwake:
    """Hold off the screensaver while a transfer runs. `caffeinate -w <pid>`
    exits with this process even on a kill, where a finally block would not."""

    def __init__(self):
        self._proc = None

    def on(self) -> None:
        if self._proc is not None or platform.system() != "Darwin":
            return
        try:
            self._proc = subprocess.Popen(["caffeinate", "-di", "-w", str(os.getpid())])
        except OSError:
            self._proc = None

    def off(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None


def save_dialog(default_name: str) -> str | None:
    """A native Save panel. macOS via osascript (Standard Additions, no
    automation permission). Returns a path or None if cancelled."""
    if platform.system() != "Darwin":
        return None
    script = (f'POSIX path of (choose file name with prompt '
              f'"Save the received file" default name "{default_name}")')
    try:
        done = subprocess.run(["osascript", "-e", script],
                              capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired):
        return None
    path = done.stdout.strip()
    return path if done.returncode == 0 and path else None
