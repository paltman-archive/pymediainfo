# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring,
# pylint: disable=protected-access

import functools
import http.server
import json
import os
import pathlib
import pickle
import re
import sys
import tempfile
import threading
import unittest
from xml.etree import ElementTree as ET

import pytest

from pymediainfo import MediaInfo

data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
test_media_files: list[str] = [
    "sample.mkv",
    "sample.mp4",
    "sample_with_cover.mp3",
    "mpeg4.mp4",
    "mp3.mp3",
    "mp4-with-audio.mp4",
]


def _get_library_version() -> tuple[str, tuple[int, ...]]:
    lib, handle, lib_version_str, lib_version = MediaInfo._get_library()
    lib.MediaInfo_Close(handle)
    lib.MediaInfo_Delete(handle)
    return lib_version_str, lib_version


class MediaInfoTest(unittest.TestCase):
    def setUp(self) -> None:
        with open(os.path.join(data_dir, "sample.xml"), encoding="utf-8") as f:
            self.xml_data = f.read()
        self.media_info = MediaInfo(self.xml_data)

    def test_populate_tracks(self) -> None:
        assert len(self.media_info.tracks) == 4

    def test_valid_video_track(self) -> None:
        for track in self.media_info.tracks:
            if track.track_type == "Video":
                assert track.codec == "DV"
                assert track.scan_type == "Interlaced"
                break

    def test_track_integer_attributes(self) -> None:
        for track in self.media_info.tracks:
            if track.track_type == "Audio":
                assert isinstance(track.duration, int)
                assert isinstance(track.bit_rate, int)
                assert isinstance(track.sampling_rate, int)
                break

    def test_track_other_attributes(self) -> None:
        general_tracks = [
            track for track in self.media_info.tracks if track.track_type == "General"
        ]
        general_track = general_tracks[0]
        assert len(general_track.other_file_size) == 5
        assert general_track.other_duration == ["1mn 1s", "1mn 1s 394ms", "1mn 1s", "00:01:01.394"]

    def test_track_existing_other_attributes(self) -> None:
        with open(os.path.join(data_dir, "issue100.xml"), encoding="utf-8") as f:
            media_info = MediaInfo(f.read())
        general_tracks = [track for track in media_info.tracks if track.track_type == "General"]
        general_track = general_tracks[0]
        assert general_track.other_format_list == "RTP / RTP"

    def test_load_mediainfo_from_string(self) -> None:
        assert len(self.media_info.tracks) == 4

    def test_getting_attribute_that_doesnot_exist(self) -> None:
        assert self.media_info.tracks[0].does_not_exist is None


class MediaInfoInvalidXMLTest(unittest.TestCase):
    def setUp(self) -> None:
        with open(os.path.join(data_dir, "invalid.xml"), encoding="utf-8") as f:
            self.xml_data = f.read()

    def test_parse_invalid_xml(self) -> None:
        with pytest.raises(ET.ParseError):
            MediaInfo(self.xml_data)


class MediaInfoLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media_info = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"))
        self.non_full_mi = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"), full=False)

    def test_can_parse_true(self) -> None:
        assert MediaInfo.can_parse()

    def test_track_count(self) -> None:
        assert len(self.media_info.tracks) == 3

    def test_track_types(self) -> None:
        assert self.media_info.tracks[1].track_type == "Video"
        assert self.media_info.tracks[2].track_type == "Audio"

    def test_track_details(self) -> None:
        assert self.media_info.tracks[1].format == "AVC"
        assert self.media_info.tracks[2].format == "AAC"
        assert self.media_info.tracks[1].duration == 958
        assert self.media_info.tracks[2].duration == 980

    def test_full_option(self) -> None:
        assert self.media_info.tracks[0].footersize == "59"
        assert self.non_full_mi.tracks[0].footersize is None

    def test_raises_on_nonexistent_library(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            nonexistent_library = os.path.join(tmp_dir, "nonexistent-libmediainfo.so")
            with pytest.raises(OSError) as exc:  # noqa: PT011
                MediaInfo.parse(
                    os.path.join(data_dir, "sample.mp4"),
                    library_file=nonexistent_library,
                )
            assert rf"Failed to load library from {nonexistent_library}" in str(exc.value)


class MediaInfoFileLikeTest(unittest.TestCase):
    def test_can_parse(self) -> None:
        with open(os.path.join(data_dir, "sample.mp4"), "rb") as f:
            MediaInfo.parse(f)

    def test_raises_on_text_mode_even_with_text(self) -> None:
        path = os.path.join(data_dir, "sample.xml")
        with open(path, encoding="utf-8") as f, pytest.raises(ValueError):  # noqa: PT011
            MediaInfo.parse(f)

    def test_raises_on_text_mode(self) -> None:
        path = os.path.join(data_dir, "sample.mkv")
        with open(path, encoding="utf-8") as f, pytest.raises(ValueError):  # noqa: PT011
            MediaInfo.parse(f)


class MediaInfoUnicodeXMLTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media_info = MediaInfo.parse(os.path.join(data_dir, "sample.mkv"))

    def test_parse_file_with_unicode_tags(self) -> None:
        expected = (
            "Dès Noël où un zéphyr haï me vêt de glaçons "
            "würmiens je dîne d’exquis rôtis de bœuf au kir à "  # noqa: RUF001
            "l’aÿ d’âge mûr & cætera !"  # noqa: RUF001
        )
        assert self.media_info.tracks[0].title == expected


class MediaInfoUnicodeFileNameTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media_info = MediaInfo.parse(os.path.join(data_dir, "accentué.txt"))

    def test_parse_unicode_file(self) -> None:
        assert len(self.media_info.tracks) == 1


@pytest.mark.skipif(
    sys.version_info < (3, 7),
    reason="SimpleHTTPRequestHandler's 'directory' argument was added in Python 3.7",
)
class MediaInfoURLTest(unittest.TestCase):
    def setUp(self) -> None:
        HandlerClass = functools.partial(  # pylint: disable=invalid-name
            http.server.SimpleHTTPRequestHandler,
            directory=data_dir,
        )
        # Pick a random port so that parallel tests (e.g. via 'tox -p') do not clash
        self.httpd = http.server.HTTPServer(("", 0), HandlerClass)
        port = self.httpd.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/sample.mkv"
        threading.Thread(target=self.httpd.serve_forever).start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def test_parse_url(self) -> None:
        media_info = MediaInfo.parse(self.url)
        assert len(media_info.tracks) == 3


class MediaInfoPathlibTest(unittest.TestCase):
    def test_parse_pathlib_path(self) -> None:
        path = pathlib.Path(data_dir) / "sample.mp4"
        media_info = MediaInfo.parse(path)
        assert len(media_info.tracks) == 3

    def test_parse_non_existent_path_pathlib(self) -> None:
        path = pathlib.Path(data_dir) / "this file does not exist"
        with pytest.raises(FileNotFoundError):
            MediaInfo.parse(path)


class MediaInfoTestParseNonExistentFile(unittest.TestCase):
    def test_parse_non_existent_path(self) -> None:
        path = os.path.join(data_dir, "this file does not exist")
        with pytest.raises(FileNotFoundError):
            MediaInfo.parse(path)


class MediaInfoCoverDataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cover_mi = MediaInfo.parse(
            os.path.join(data_dir, "sample_with_cover.mp3"), cover_data=True
        )
        self.no_cover_mi = MediaInfo.parse(os.path.join(data_dir, "sample_with_cover.mp3"))

    def test_parse_cover_data(self) -> None:
        expected = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACXBIWXMAAAAAAA"
            "AAAQCEeRdzAAAADUlEQVR4nGP4x8DwHwAE/AH+QSRCQgAAAABJRU5ErkJggg=="
        )
        assert self.cover_mi.tracks[0].cover_data == expected

    def test_parse_no_cover_data(self) -> None:
        lib_version_str, lib_version = _get_library_version()
        if lib_version < (18, 3):
            pytest.skip(
                "The Cover_Data option is not supported by this library version "
                f"(v{lib_version_str} detected, v18.03 required)"
            )
        assert self.no_cover_mi.tracks[0].cover_data is None


class MediaInfoTrackParsingTest(unittest.TestCase):
    def test_track_parsing(self) -> None:
        media_info = MediaInfo.parse(os.path.join(data_dir, "issue55.flv"))
        assert len(media_info.tracks) == 2


class MediaInfoRuntimeErrorTest(unittest.TestCase):
    def test_parse_invalid_url(self) -> None:
        # This is the easiest way to cause a parsing error
        # since non-existent files return a different exception
        with pytest.raises(RuntimeError):
            MediaInfo.parse("unsupportedscheme://")


class MediaInfoSlowParseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media_info = MediaInfo.parse(
            os.path.join(data_dir, "vbr_requires_parsespeed_1.mp4"), parse_speed=1
        )

    def test_slow_parse_speed(self) -> None:
        assert self.media_info.tracks[2].stream_size == "3353 / 45"


class MediaInfoEqTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mp3_mi = MediaInfo.parse(os.path.join(data_dir, "sample_with_cover.mp3"))
        self.mp3_other_mi = MediaInfo.parse(os.path.join(data_dir, "sample_with_cover.mp3"))
        self.mp4_mi = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"))

    def test_eq(self) -> None:
        assert self.mp3_mi.tracks[0] == self.mp3_other_mi.tracks[0]
        assert self.mp3_mi == self.mp3_other_mi
        assert self.mp3_mi.tracks[0] != self.mp4_mi.tracks[0]
        assert self.mp3_mi != self.mp4_mi

    def test_pickle_unpickle(self) -> None:
        pickled_track = pickle.dumps(self.mp4_mi.tracks[0])
        assert self.mp4_mi.tracks[0] == pickle.loads(pickled_track)
        pickled_mi = pickle.dumps(self.mp4_mi)
        assert self.mp4_mi == pickle.loads(pickled_mi)


class MediaInfoLegacyStreamDisplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.media_info = MediaInfo.parse(os.path.join(data_dir, "aac_he_v2.aac"))
        self.legacy_mi = MediaInfo.parse(
            os.path.join(data_dir, "aac_he_v2.aac"), legacy_stream_display=True
        )

    def test_legacy_stream_display(self) -> None:
        assert self.media_info.tracks[1].channel_s == 2
        assert self.legacy_mi.tracks[1].channel_s == "2 / 1 / 1"


class MediaInfoOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        lib_version_str, lib_version = _get_library_version()
        if lib_version < (19, 9):
            pytest.skip(
                "The Reset option is not supported by this library version "
                f"(v{lib_version_str} detected, v19.09 required)"
            )
        self.raw_language_mi = MediaInfo.parse(
            os.path.join(data_dir, "sample.mkv"),
            mediainfo_options={"Language": "raw"},
        )
        # Parsing the file without the custom options afterwards
        # allows us to check that the "Reset" option worked
        # https://github.com/MediaArea/MediaInfoLib/issues/1128
        self.normal_mi = MediaInfo.parse(
            os.path.join(data_dir, "sample.mkv"),
        )

    def test_mediainfo_options(self) -> None:
        assert self.normal_mi.tracks[1].other_language[0] == "English"
        assert self.raw_language_mi.tracks[1].language == "en"


# Unittests can't be parametrized
# https://github.com/pytest-dev/pytest/issues/541
@pytest.mark.parametrize("test_file", test_media_files)
def test_thread_safety(test_file: str) -> None:
    lib_version_str, lib_version = _get_library_version()
    if lib_version < (20, 3):
        pytest.skip(
            "This version of the library is not thread-safe "
            f"(v{lib_version_str} detected, v20.03 required)"
        )
    expected_result = MediaInfo.parse(os.path.join(data_dir, test_file))
    results = []
    lock = threading.Lock()

    def target() -> None:
        try:
            result = MediaInfo.parse(os.path.join(data_dir, test_file))
            with lock:
                results.append(result)
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            pass

    threads = []
    thread_count = 100
    for _ in range(thread_count):
        thread = threading.Thread(target=target)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    # Each thread should have produced a result
    assert len(results) == thread_count
    for res in results:
        # Test dicts first because they will show a diff
        # in case they don't match
        assert res.to_data() == expected_result.to_data()
        assert res == expected_result


@pytest.mark.parametrize("test_file", test_media_files)
def test_filelike_returns_the_same(test_file: str) -> None:
    filename = os.path.join(data_dir, test_file)
    mi_from_filename = MediaInfo.parse(filename)
    with open(filename, "rb") as f:
        mi_from_file = MediaInfo.parse(f)
    assert len(mi_from_file.tracks) == len(mi_from_filename.tracks)
    for track_from_file, track_from_filename in zip(mi_from_file.tracks, mi_from_filename.tracks):
        # The General track will differ, typically not giving the file name
        if track_from_file.track_type != "General":
            # Test dicts first because they will produce a diff
            assert track_from_file.to_data() == track_from_filename.to_data()
            assert track_from_file == track_from_filename


class MediaInfoOutputTest(unittest.TestCase):
    def test_text_output(self) -> None:
        media_info = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"), output="")
        assert re.search(r"Stream size\s+: 373836\b", media_info)

    def test_json_output(self) -> None:
        lib_version_str, lib_version = _get_library_version()
        if lib_version < (18, 3):
            pytest.skip(
                "This version of the library does not support JSON output "
                f"(v{lib_version_str} detected, v18.03 required)"
            )
        media_info = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"), output="JSON")
        parsed = json.loads(media_info)
        assert parsed["media"]["track"][0]["FileSize"] == "404567"

    def test_parameter_output(self) -> None:
        media_info = MediaInfo.parse(
            os.path.join(data_dir, "sample.mp4"), output="General;%FileSize%"
        )
        assert media_info == "404567"


class MediaInfoTrackShortcutsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mi_audio = MediaInfo.parse(os.path.join(data_dir, "sample.mp4"))
        self.mi_text = MediaInfo.parse(os.path.join(data_dir, "sample.mkv"))
        self.mi_image = MediaInfo.parse(os.path.join(data_dir, "empty.gif"))
        with open(os.path.join(data_dir, "other_track.xml"), encoding="utf-8") as f:
            self.mi_other = MediaInfo(f.read())

    def test_empty_list(self) -> None:
        assert self.mi_audio.text_tracks == []

    def test_general_tracks(self) -> None:
        assert len(self.mi_audio.general_tracks) == 1
        assert self.mi_audio.general_tracks[0].file_name is not None

    def test_video_tracks(self) -> None:
        assert len(self.mi_audio.video_tracks) == 1
        assert self.mi_audio.video_tracks[0].display_aspect_ratio is not None

    def test_audio_tracks(self) -> None:
        assert len(self.mi_audio.audio_tracks) == 1
        assert self.mi_audio.audio_tracks[0].sampling_rate is not None

    def test_text_tracks(self) -> None:
        assert len(self.mi_text.text_tracks) == 1
        assert self.mi_text.text_tracks[0].kind_of_stream == "Text"

    def test_other_tracks(self) -> None:
        assert len(self.mi_other.other_tracks) == 2
        assert self.mi_other.other_tracks[0].type == "Time code"

    def test_image_tracks(self) -> None:
        assert len(self.mi_image.image_tracks) == 1
        assert self.mi_image.image_tracks[0].width == 1

    def test_menu_tracks(self) -> None:
        assert len(self.mi_text.menu_tracks) == 1
        assert self.mi_text.menu_tracks[0].kind_of_stream == "Menu"
