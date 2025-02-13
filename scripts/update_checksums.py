#!/usr/bin/env python3

# ruff: noqa: T201, E402
"""Update the bundled MediaInfo version and checksums in the pyproject.toml file."""

import argparse
import sys
from pathlib import Path

import requests

script_folder = Path(__file__).resolve().parent
sys.path.append(str(script_folder))

from download_library import get_file_hashes
from mediainfo_config import get_version, modify_config, update_config_version

#: API to fetch the latest release of MediaInfo
LATEST_RELEASE_URL = "https://api.github.com/repos/MediaArea/MediaInfo/releases/latest"


def get_last_version(*, timeout: int = 20) -> str:
    """Fetch the value of the latest MediaInfo version from the Github repo."""
    # Fetch the latest release using Github API
    response = requests.get(LATEST_RELEASE_URL, timeout=timeout)
    response.raise_for_status()
    json = response.json()

    if "name" not in json:
        msg = f"cannot read the version of the latest MediaInfo release:\n{json}"
        raise ValueError(msg)

    return str(json["name"])


def update_version(*, timeout: int = 20, verbose: bool = True) -> str:
    """Update the version of the bundled mediainfo library."""
    # Get latest version
    latest_version = get_last_version(timeout=timeout)

    # Get version from config file
    version = get_version()

    # If already latest version, early return
    if version == latest_version:
        return latest_version

    # Update version in pyproject.toml
    update_config_version(latest_version, verbose=verbose)

    return latest_version


def update_hashes(*, update_version: bool = False, timeout: int = 20, verbose: bool = True) -> None:
    """Update the hashes of the downloaded mediainfo library."""
    with modify_config(verbose=verbose) as media_info_config:
        version = media_info_config["version"]

        if update_version:
            # Get latest version
            new_version = get_last_version(timeout=timeout)
            if new_version != version:
                if verbose:
                    print(f"Update MediaInfo {version} -> {new_version}")
                version = new_version
            media_info_config["version"] = version

        for info in media_info_config["wheel"]:
            # Update checksums
            try:
                checksums = get_file_hashes(
                    version,
                    info["platform"],
                    info["arch"],
                )
            except Exception as e:  # noqa: BLE001
                if verbose:
                    print(e)
            else:
                info["blake2b_sums"] = checksums


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-V",
        "--only-version",
        help="only update the version",
        action="store_true",
    )
    parser.add_argument(
        "-C",
        "--only-checksums",
        help="only update the checksums",
        action="store_true",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        help="hide progress messages",
        action="store_true",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="URL request timeout in seconds",
        default=20,
    )

    args = parser.parse_args()

    if args.only_version:
        update_version(timeout=args.timeout, verbose=not args.quiet)
    else:
        update_hashes(
            update_version=not args.only_checksums,
            timeout=args.timeout,
            verbose=not args.quiet,
        )
