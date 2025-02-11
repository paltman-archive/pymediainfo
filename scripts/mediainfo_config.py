# ruff: noqa: T201
"""Download binary library files from <https://mediaarea.net/en/MediaInfo/Download/>."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import tomlkit

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Literal, NotRequired, TypedDict

    class BundledWheelInfo(TypedDict):
        """Info about a bundled wheel."""

        platform: Literal["linux", "darwin", "win32"]
        arch: Literal["x86_64", "arm64", "i386"]
        blake2b_sums: str
        tag: NotRequired[str]
        cli_source: NotRequired[bool]

    class MediainfoConfigDict(TypedDict):
        """Configuration of the bundled wheels."""

        version: str
        wheel: list[BundledWheelInfo]


#: The path of the default pyproject.toml config file."""
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent.parent / "pyproject.toml"


def get_mediainfo_config() -> MediainfoConfigDict:
    """Read information about the MediaInfo library to bundle from pyproject.toml."""
    # read toml
    config = tomlkit.parse(DEFAULT_CONFIG_FILE.read_text(encoding="utf-8"))
    media_info_config = config["tool"].setdefault("bundled_libmediainfo", {})  # type: ignore[union-attr]

    # check config
    if "version" not in media_info_config:
        msg = (
            "mandatory key 'version' missing from [tool.bundled_libmediainfo] "
            f"in {DEFAULT_CONFIG_FILE}"
        )
        raise ValueError(msg)

    if "wheel" not in media_info_config:
        msg = (
            f"mandatory table missing [[tool.bundled_libmediainfo.wheel]] in {DEFAULT_CONFIG_FILE}"
        )
        raise ValueError(msg)

    return cast("MediainfoConfigDict", media_info_config)


def get_bundle_info(
    config: list[BundledWheelInfo],
    platform: str,
    arch: str,
    *,
    get_curl: bool = False,
) -> BundledWheelInfo:
    """Get the information about the wheel for the specific platform and arch."""
    for info in config:
        if (
            info["platform"] == platform
            and info["arch"] == arch
            and bool(info.get("cli_source", False)) == get_curl
        ):
            return info

    # No match
    key = (platform, arch, f"get_curl={get_curl}")
    msg = f"No match for {key}"
    raise KeyError(msg)


def get_version() -> str:
    """Get Mediainfo version from the config file."""
    mediainfo_config = get_mediainfo_config()
    return mediainfo_config["version"]


def get_version_and_bundle_info(
    platform: str,
    arch: str,
    *,
    get_curl: bool = False,
) -> tuple[str, BundledWheelInfo]:
    """Get Mediainfo version and specific information for the bundled library."""
    mediainfo_config = get_mediainfo_config()
    version = mediainfo_config["version"]

    info = get_bundle_info(
        mediainfo_config["wheel"],
        platform,
        arch,
        get_curl=get_curl,
    )
    return version, info


@contextmanager
def modify_config(
    config_file: str | os.PathLike[str] | None = None,
    *,
    verbose: bool = True,
) -> Iterator[MediainfoConfigDict]:
    """Modify a the [tool.bundled_libmediainfo] section of a toml file.

    This is a context manager, any change to the yielded dict will be written in
    the file at the end. If the [tool.bundled_libmediainfo] section does not
    exist, the changed will be ignored and the toml file will not be modified.

    Example:
    >>> with modify_config() as media_info_config:
    ...     media_info_config["version"] = version

    """
    config_file = Path(config_file or DEFAULT_CONFIG_FILE)

    # Read config
    config = tomlkit.parse(config_file.read_text(encoding="utf-8"))
    if "tool" not in config or "bundled_libmediainfo" not in config["tool"]:  # type: ignore[operator]
        if verbose:
            print(
                "the [tool.bundled_libmediainfo] was not found in the config, "
                f"the file will not be modified: {os.fspath(config_file)!r}"
            )
        # yield a minimalist MediainfoConfigDict for compatibility
        yield {"version": "", "wheel": []}
        return

    media_info_config = config["tool"]["bundled_libmediainfo"]  # type: ignore[index]
    yield cast("MediainfoConfigDict", media_info_config)

    # Maybe we could output a diff of the changes
    if verbose:
        print(f"Will modify the content of {os.fspath(config_file)!r}")

    # Write modified content
    with open(config_file, "w") as f:
        f.write(tomlkit.dumps(config))


def update_config_version(version: str, *, verbose: bool = True) -> None:
    """Update MediaInfo bundled version in the config file."""
    # Read config and modify
    with modify_config(verbose=verbose) as media_info_config:
        # Update version
        media_info_config["version"] = version
