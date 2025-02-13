#!/usr/bin/env python3

# ruff: noqa: T201
"""Download binary library files from <https://mediaarea.net/en/MediaInfo/Download/>."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any
from zipfile import ZipFile

import requests

script_folder = Path(__file__).resolve().parent
sys.path.append(str(script_folder))

from mediainfo_config import get_version_and_bundle_info  # noqa: E402

if TYPE_CHECKING:
    from typing import Literal


#: Base URL for downloading MediaInfo library
BASE_URL: str = "https://mediaarea.net/download/binary/libmediainfo0"


def get_file_blake2b(file_path: os.PathLike[str] | str, chunksize: int = 1 << 20) -> str:
    """Get the BLAKE2b hash of a file."""
    blake2b = hashlib.blake2b()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunksize):
            blake2b.update(chunk)
    return blake2b.hexdigest()


@dataclass
class Downloader:
    """Downloader for the MediaInfo library files."""

    #: Version of the bundled MediaInfo library
    version: str

    #: Platform of the bundled MediaInfo library
    platform: Literal["linux", "darwin", "win32"]

    #: Architecture of the bundled MediaInfo library
    arch: Literal["x86_64", "arm64", "i386"]

    #: BLAKE2b hash of the downloaded MediaInfo library
    checksums: str | None = None

    def __post_init__(self) -> None:
        """Check that the combination of platform and arch is allowed."""
        allowed_arch = None
        if self.platform in ("linux", "darwin"):
            allowed_arch = ["x86_64", "arm64"]
        elif self.platform == "win32":
            allowed_arch = ["x86_64", "i386", "arm64"]
        else:
            msg = f"platform not recognized: {self.platform}"
            raise ValueError(msg)

        # Check the platform and arch is a valid combination
        if allowed_arch is not None and self.arch not in allowed_arch:
            msg = (
                f"arch {self.arch} is not allowed for platform {self.platform}; "
                f"must be one of {allowed_arch}"
            )
            raise ValueError(msg)

    @property
    def win_arch(self) -> str:
        """Arch for Windows as it appears in MediaInfo downloads."""
        win_arch: str = self.arch
        if self.arch == "x86_64":
            win_arch = "x64"
        elif self.arch == "arm64":
            win_arch = "ARM64"
        return win_arch

    def get_compressed_file_name(self) -> str:
        """Get the compressed library file name."""
        if self.platform == "linux":
            suffix = f"Lambda_{self.arch}.zip"
        elif self.platform == "darwin":
            suffix = "Mac_x86_64+arm64.tar.bz2"
        elif self.platform == "win32":
            suffix = f"Windows_{self.win_arch}_WithoutInstaller.zip"
        else:
            msg = f"platform not recognized: {self.platform}"
            raise ValueError(msg)

        return f"MediaInfo_DLL_{self.version}_{suffix}"

    def get_url(self, file_name: str) -> str:
        """Get the URL to download the MediaInfo library."""
        return f"{BASE_URL}/{self.version}/{file_name}"

    def compare_hash(self, h: str) -> bool:
        """Compare downloaded hash with expected."""
        # Check expected hash exists
        if self.checksums is None:
            msg = "hash was not provided."
            raise ValueError(msg)

        # Check hashes match
        if self.checksums != h:
            key = (self.platform, self.arch)
            msg = f"hash mismatch for {key}: expected {self.checksums}, got {h}"
            raise ValueError(msg)

        return True

    def download_upstream(
        self,
        url: str,
        outpath: os.PathLike[str],
        *,
        check_hash: bool = True,
        timeout: int = 20,
    ) -> str:
        """Download the compressed file from upstream URL."""
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        with open(outpath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        downloaded_hash = get_file_blake2b(outpath)
        if check_hash:
            self.compare_hash(downloaded_hash)
        return downloaded_hash

    def unpack(
        self,
        file: os.PathLike[str] | str,
        folder: os.PathLike[str] | str,
    ) -> dict[str, str]:
        """Extract compressed files."""
        file = Path(file)
        folder = Path(folder)

        if not file.is_file():
            msg = f"compressed file not found: {file.name!r}"
            raise ValueError(msg)
        tmp_dir = file.parent

        license_file: Path | None = None
        lib_file: Path | None = None

        # Linux
        if file.name.endswith(".zip") and self.platform == "linux":
            with ZipFile(file) as fd:
                license_file = folder / "LICENSE"
                fd.extract("LICENSE", tmp_dir)
                shutil.move(os.fspath(tmp_dir / "LICENSE"), os.fspath(license_file))

                lib_file = folder / "libmediainfo.so.0"
                fd.extract("lib/libmediainfo.so.0.0.0", tmp_dir)
                shutil.move(os.fspath(tmp_dir / "lib/libmediainfo.so.0.0.0"), os.fspath(lib_file))

        # macOS (darwin)
        elif file.name.endswith(".tar.bz2") and self.platform == "darwin":
            with tarfile.open(file) as fd:
                kwargs: dict[str, Any] = {}
                # Set for security reasons, see
                # https://docs.python.org/3/library/tarfile.html#tarfile-extraction-filter
                if sys.version_info >= (3, 12):
                    kwargs = {"filter": "data"}

                license_file = folder / "License.html"
                fd.extract("MediaInfoLib/License.html", tmp_dir, **kwargs)
                shutil.move(
                    os.fspath(tmp_dir / "MediaInfoLib/License.html"),
                    os.fspath(license_file),
                )

                lib_file = folder / "libmediainfo.0.dylib"
                fd.extract("MediaInfoLib/libmediainfo.0.dylib", tmp_dir, **kwargs)
                shutil.move(
                    os.fspath(tmp_dir / "MediaInfoLib/libmediainfo.0.dylib"),
                    os.fspath(lib_file),
                )

        # Windows (win32)
        elif file.name.endswith(".zip") and self.platform == "win32":
            with ZipFile(file) as fd:
                license_file = folder / "License.html"
                fd.extract("Developers/License.html", tmp_dir)
                shutil.move(
                    os.fspath(tmp_dir / "Developers/License.html"),
                    os.fspath(license_file),
                )

                lib_file = folder / "MediaInfo.dll"
                fd.extract("MediaInfo.dll", tmp_dir)
                shutil.move(os.fspath(tmp_dir / "MediaInfo.dll"), os.fspath(lib_file))

        files = {}
        if license_file is not None and license_file.is_file():
            files["license"] = os.fspath(license_file.relative_to(folder))
        if lib_file is not None and lib_file.is_file():
            files["lib"] = os.fspath(lib_file.relative_to(folder))

        return files

    def download(
        self,
        folder: os.PathLike[str] | str,
        *,
        check_hash: bool = True,
        timeout: int = 20,
        verbose: bool = True,
    ) -> dict[str, str]:
        """Download the library and license files."""
        folder = Path(folder)

        compressed_file = self.get_compressed_file_name()
        url = self.get_url(compressed_file)

        extracted_files = {}
        with TemporaryDirectory() as tmp_dir:
            outpath = Path(tmp_dir) / compressed_file
            if verbose:
                print(f"Downloading MediaInfo library from {url}")
            self.download_upstream(
                url,
                outpath,
                check_hash=check_hash,
                timeout=timeout,
            )

            if verbose:
                print(f"Extracting {compressed_file}")
            extracted_files = self.unpack(outpath, folder)

            if verbose:
                print(f"Extracted files: {extracted_files}")
        return extracted_files

    def get_downloaded_hash(
        self,
        *,
        timeout: int = 20,
        verbose: bool = True,
    ) -> str:
        """Get the hash of the downloaded file."""
        compressed_file = self.get_compressed_file_name()
        url = self.get_url(compressed_file)

        with TemporaryDirectory() as tmp_dir:
            outpath = Path(tmp_dir) / compressed_file
            if verbose:
                print(f"Downloading MediaInfo library from {url}")
            return self.download_upstream(
                url,
                outpath,
                timeout=timeout,
                check_hash=False,
            )


def download_files(
    folder: os.PathLike[str] | str,
    version: str,
    platform: Literal["linux", "darwin", "win32"],
    arch: Literal["x86_64", "arm64", "i386"],
    *,
    checksums: str | None = None,
    timeout: int = 20,
    verbose: bool = True,
) -> dict[str, str]:
    """Download the library and license files to the output folder."""
    # Download
    downloader = Downloader(
        version=version,
        platform=platform,
        arch=arch,
        checksums=checksums,
    )
    return downloader.download(folder, timeout=timeout, verbose=verbose)


def get_file_hashes(
    version: str,
    platform: Literal["linux", "darwin", "win32"],
    arch: Literal["x86_64", "arm64", "i386"],
    *,
    timeout: int = 20,
    verbose: bool = True,
) -> str:
    """Download the library and license files to the output folder."""
    downloader = Downloader(version=version, platform=platform, arch=arch)
    return downloader.get_downloaded_hash(timeout=timeout, verbose=verbose)


def clean_files(
    folder: os.PathLike[str] | str,
    *,
    verbose: bool = True,
) -> bool:
    """Remove downloaded files in the output folder."""
    folder = Path(folder)
    if not folder.is_dir():
        if verbose:
            print(f"folder does not exist: {os.fspath(folder)!r}")
        return False

    glob_patterns = [
        "License.html",
        "LICENSE",
        "MediaInfo.dll",
        "libmediainfo.*",
    ]

    # list files to delete
    to_delete: list[os.PathLike[str]] = []
    for pattern in glob_patterns:
        to_delete.extend(folder.glob(pattern))

    # delete files
    if verbose:
        print(f"will delete files: {to_delete}")
    for relative_path in to_delete:
        (folder / relative_path).unlink()

    return True


def make_parser() -> argparse.ArgumentParser:
    """Make the argument parser."""
    default_folder = Path(__file__).resolve().parent.parent / "src" / "pymediainfo"

    parser = argparse.ArgumentParser(
        description="download MediaInfo files from upstream.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

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
        "-A",
        "--auto",
        action="store_true",
        help="use the current platform and architecture",
    )
    parser.add_argument(
        "-s",
        "--print-sums",
        help="download the file from upstream and return the BLAKE2b hash",
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
    parser.add_argument(
        "-o",
        "--folder",
        type=Path,
        help="output folder",
        default=default_folder,
    )
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="clean the output folder of downloaded files.",
    )

    return parser


if __name__ == "__main__":
    import platform

    parser = make_parser()
    args = parser.parse_args()

    if not any((args.auto, args.clean, args.platform and args.arch)):
        parser.error("either -A/--auto, -c/--clean or -a/--arch with -p/--platform must be used")

    if not args.folder.is_dir():
        parser.error(f"{args.folder} does not exist or is not a folder")

    if args.auto:
        args.platform = platform.system().lower()
        args.arch = platform.machine().lower()

    # Clean folder
    if args.clean:
        clean_files(args.folder, verbose=not args.quiet)

    # Exit if no platform-arch was provided
    if args.platform is None or args.arch is None:
        sys.exit(0)

    # Get version
    version, info = get_version_and_bundle_info(args.platform, args.arch)
    # Get checksums
    checksums = info["blake2b_sums"]

    # Print the checksums and exit
    if args.print_sums:
        checksums = get_file_hashes(
            version,
            args.platform,
            args.arch,
            timeout=args.timeout,
            verbose=not args.quiet,
        )
        print(checksums)
        sys.exit(0)

    # Download files
    download_files(
        args.folder,
        version,
        args.platform,
        args.arch,
        checksums=checksums,
        verbose=not args.quiet,
        timeout=args.timeout,
    )

    sys.exit(0)
