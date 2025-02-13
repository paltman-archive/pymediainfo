#!/usr/bin/env python3

# ruff: noqa: T201
"""Tags all pure Python wheels from the 'dist' folder."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from wheel.cli.tags import tags  # type: ignore[import-untyped]

script_folder = Path(__file__).resolve().parent
sys.path.append(str(script_folder))

from mediainfo_config import get_version_and_bundle_info  # noqa: E402

if TYPE_CHECKING:
    import os

#: Default 'dist' directory
DEFAULT_DIST_DIR = Path(__file__).resolve().parent.parent / "dist"


def tag_wheel(
    platform_tag: str,
    folder: str | os.PathLike[str] | None = None,
    *,
    match: str = "*-py3-none-any.whl",
    verbose: bool = True,
) -> list[str]:
    """Tag the wheels in folder with new platform tags."""
    dist_dir = Path(folder or DEFAULT_DIST_DIR)

    new_wheels = []
    for wheel_path in dist_dir.glob(match):
        new_wheel = tags(wheel_path, platform_tags=platform_tag, remove=True)
        if verbose:
            print(f"Tagged {wheel_path.name} -> {new_wheel}")
        new_wheels.append(new_wheel)

    return new_wheels


if __name__ == "__main__":
    import argparse
    import platform

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-p",
        "--platform",
        choices=["linux", "darwin", "win32"],
        help="platform of the library",
    )
    parser.add_argument(
        "-a",
        "--arch",
        choices=["x86_64", "arm64", "i386"],
        help="architecture of the library",
    )
    parser.add_argument(
        "--platform_tag",
        help="the tag to add",
    )
    parser.add_argument(
        "-A",
        "--auto",
        action="store_true",
        help="use the current platform and architecture",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="hide progress messages",
        action="store_true",
    )
    args = parser.parse_args()

    if not any((args.auto, args.platform and args.arch)):
        parser.error("either -A/--auto, or -a/--arch with -p/--platform must be used")

    if args.auto:
        args.platform = platform.system().lower()
        args.arch = platform.machine().lower()

    # Get platform_tag from pyproject.toml
    if not args.platform_tag:
        version, info = get_version_and_bundle_info(args.platform, args.arch)
        if "tag" not in info:
            msg = f"platform tag was not defined in the configuration file: {info}"
            raise ValueError(msg)
        args.platform_tag = info["tag"]

    # Tag the wheels with a new platform tag
    tag_wheel(args.platform_tag, verbose=not args.quiet)
