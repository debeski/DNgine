from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from first_party_packages.media_images.plugins.smart_background_remover import apply_background_removal, run_smart_background_task
from first_party_packages.media_images.plugins.smart_exif_editor import run_smart_exif_task, undo_smart_exif_task


class _DummyContext:
    def __init__(self):
        self.logs: list[tuple[str, str]] = []
        self.progress_values: list[float] = []

    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append((level, message))

    def progress(self, value: float) -> None:
        self.progress_values.append(float(value))


class _DummyServices:
    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)
        self.data_root.mkdir(parents=True, exist_ok=True)

    def plugin_text(self, _plugin_id: str, _key: str, default: str | None = None, **kwargs) -> str:
        template = default or ""
        return template.format(**kwargs) if kwargs else template


def _read_exif(path: Path):
    with Image.open(path) as image:
        return image.getexif()


def _write_test_jpeg(
    path: Path,
    *,
    description: str,
    artist: str = "",
    copyright: str = "",
    make: str = "Canon",
    model: str = "EOS",
) -> None:
    image = Image.new("RGB", (32, 32), (240, 240, 240))
    exif = Image.Exif()
    exif[270] = description
    exif[315] = artist
    exif[33432] = copyright
    exif[271] = make
    exif[272] = model
    exif[306] = "2024:01:01 10:00:00"
    image.save(path, exif=exif)


class MediaPluginTaskTests(unittest.TestCase):
    def test_background_remover_writes_transparent_png(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            source_path = temp_root / "source.png"
            output_dir = temp_root / "output"

            image = Image.new("RGB", (80, 80), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 20, 60, 60), fill=(220, 40, 40))
            image.save(source_path)

            result = run_smart_background_task(
                _DummyContext(),
                [str(source_path)],
                str(output_dir),
                {
                    "strategy": "edge",
                    "background_mode": "transparent",
                    "custom_color": "#ffffff",
                    "crop_to_subject": False,
                },
            )

            self.assertEqual(result["count"], 1)
            output_path = Path(result["files"][0])
            self.assertTrue(output_path.exists())
            rendered = Image.open(output_path).convert("RGBA")
            self.assertLess(rendered.getpixel((0, 0))[3], 10)
            self.assertGreater(rendered.getpixel((40, 40))[3], 200)

    def test_background_remover_preview_mode_stays_image_shaped(self) -> None:
        image = Image.new("RGB", (1800, 1200), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((420, 180, 1380, 1080), fill=(20, 120, 220))

        rendered, notes = apply_background_removal(
            image,
            strategy="auto",
            background_mode="transparent",
            custom_color="#ffffff",
            crop_to_subject=False,
            allow_ai=False,
            preview_mode=True,
        )

        self.assertEqual(rendered.size, image.size)
        self.assertEqual(notes, [])
        self.assertLess(rendered.convert("RGBA").getpixel((0, 0))[3], 20)

    def test_background_remover_large_images_log_reduced_mask_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            source_path = temp_root / "large.png"
            output_dir = temp_root / "output"
            context = _DummyContext()

            image = Image.new("RGB", (2600, 1800), (255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((520, 300, 2080, 1500), fill=(200, 30, 60))
            image.save(source_path)

            result = run_smart_background_task(
                context,
                [str(source_path)],
                str(output_dir),
                {
                    "strategy": "edge",
                    "background_mode": "transparent",
                    "custom_color": "#ffffff",
                    "crop_to_subject": False,
                },
            )

            self.assertEqual(result["count"], 1)
            self.assertTrue(any("Large image detected" in message for _level, message in context.logs))

    def test_smart_exif_copy_mode_preserves_original_and_strips_camera_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            services = _DummyServices(temp_root / "data")
            source_path = temp_root / "photo.jpg"
            output_dir = temp_root / "output"
            _write_test_jpeg(source_path, description="before", artist="before-artist", copyright="before-copyright")

            result = run_smart_exif_task(
                _DummyContext(),
                services,
                "smart_exif",
                [str(source_path)],
                "copy",
                {
                    "description": "after",
                    "artist": "after-artist",
                    "copyright": "",
                    "date_time": "2026-04-04 14:30",
                    "clear_gps": False,
                    "clear_camera": True,
                    "strip_non_essential": False,
                },
                str(output_dir),
            )

            self.assertEqual(result["count"], 1)
            original_exif = _read_exif(source_path)
            copied_exif = _read_exif(Path(result["files"][0]))
            self.assertEqual(str(original_exif.get(270)), "before")
            self.assertEqual(str(copied_exif.get(270)), "after")
            self.assertEqual(str(copied_exif.get(315)), "after-artist")
            self.assertEqual(str(copied_exif.get(33432)), "before-copyright")
            self.assertNotIn(271, copied_exif)
            self.assertNotIn(272, copied_exif)

    def test_smart_exif_copy_mode_can_explicitly_clear_selected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            services = _DummyServices(temp_root / "data")
            source_path = temp_root / "photo.jpg"
            output_dir = temp_root / "output"
            _write_test_jpeg(
                source_path,
                description="before",
                artist="before-artist",
                copyright="before-copyright",
            )

            result = run_smart_exif_task(
                _DummyContext(),
                services,
                "smart_exif",
                [str(source_path)],
                "copy",
                {
                    "description": "",
                    "artist": "",
                    "copyright": "",
                    "date_time": "",
                    "clear_description": False,
                    "clear_artist": True,
                    "clear_copyright": False,
                    "clear_datetime": True,
                    "clear_gps": False,
                    "clear_camera": False,
                    "strip_non_essential": False,
                },
                str(output_dir),
            )

            copied_exif = _read_exif(Path(result["files"][0]))
            self.assertEqual(str(copied_exif.get(270)), "before")
            self.assertNotIn(315, copied_exif)
            self.assertEqual(str(copied_exif.get(33432)), "before-copyright")
            self.assertNotIn(306, copied_exif)

    def test_smart_exif_in_place_mode_supports_last_run_undo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            services = _DummyServices(temp_root / "data")
            source_path = temp_root / "photo.jpg"
            _write_test_jpeg(source_path, description="original")

            result = run_smart_exif_task(
                _DummyContext(),
                services,
                "smart_exif",
                [str(source_path)],
                "in_place",
                {
                    "description": "updated",
                    "artist": "",
                    "copyright": "",
                    "date_time": "",
                    "clear_gps": False,
                    "clear_camera": False,
                    "strip_non_essential": False,
                },
            )

            self.assertEqual(result["count"], 1)
            self.assertTrue(result["undo_available"])
            self.assertEqual(str(_read_exif(source_path).get(270)), "updated")

            undo_result = undo_smart_exif_task(_DummyContext(), services, "smart_exif")
            self.assertEqual(undo_result["restored_count"], 1)
            self.assertEqual(undo_result["error_count"], 0)
            self.assertEqual(str(_read_exif(source_path).get(270)), "original")


if __name__ == "__main__":
    unittest.main()
