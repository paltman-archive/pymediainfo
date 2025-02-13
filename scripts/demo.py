#!/usr/bin/env python3
# ruff: noqa: T201, T203
"""A demo that shows how to call pymediainfo."""

from __future__ import annotations

from pprint import pprint

from pymediainfo import MediaInfo


def process(media_file: str) -> None:
    """Process the file."""
    print(f"Processing {media_file}")
    media_info = MediaInfo.parse(media_file)
    for track in media_info.tracks:
        if track.track_type == "General":
            print(f"The file format is {track.format}")
            print("General information dump:")
            pprint(track.to_data())
        elif track.track_type == "Video":
            print(
                f"Video track {track.track_id} has a resolution of {track.width}×{track.height}",  # noqa: RUF001
                f"and a bit rate of {track.bit_rate} bits/s",
            )
        elif track.track_type == "Audio":
            if track.duration is not None:
                print(
                    f"Audio track {track.track_id} has a duration of "
                    f"{track.duration / 1000} seconds"
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_file", nargs="+", help="media files to parse")
    args = parser.parse_args()

    for index, media_file in enumerate(args.media_file):
        if index != 0:
            print()
        process(media_file)
