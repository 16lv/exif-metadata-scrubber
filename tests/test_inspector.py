from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from image_metadata.inspector import (
    GPS_TAG_ID,
    inspect_image,
    main,
    scrub_directory,
    strip_metadata_to_copy,
)


def test_inspect_and_strip_exif_and_gps_preserves_original_file(tmp_path: Path) -> None:
    img_path = tmp_path / "sample_with_exif.jpg"
    clean_path = tmp_path / "sample_cleaned.jpg"

    img = Image.new("RGB", (64, 48), color=(30, 60, 90))
    exif = img.getexif()
    exif[271] = "TestCamera-A1"
    exif[272] = "Model-X1"
    exif[305] = "exif-scrubber-tests"
    exif[GPS_TAG_ID] = {1: "N", 3: "W"}
    img.save(img_path, format="JPEG", exif=exif.tobytes())

    report = inspect_image(img_path)
    assert report.width == 64
    assert report.height == 48
    assert report.format == "JPEG"
    assert report.has_exif is True
    assert report.has_gps_info is True
    assert report.gps_summary.get("GPSLatitudeRef") == "N"
    assert report.exif_fields.get("Make") == "TestCamera-A1"

    summary = strip_metadata_to_copy(img_path, clean_path)
    assert summary["removed_exif_field_count"] >= 3
    assert summary["removed_gps_data"] is True
    assert summary["output_has_exif"] is False

    assert inspect_image(img_path).has_exif is True
    cleaned_report = inspect_image(clean_path)
    assert cleaned_report.has_exif is False
    assert cleaned_report.has_gps_info is False
    assert cleaned_report.exif_fields == {}


def test_inspect_image_without_exif_and_reject_corrupt_files(tmp_path: Path) -> None:
    png_path = tmp_path / "plain.png"
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(png_path, format="PNG")

    rep = inspect_image(png_path)
    assert rep.format == "PNG"
    assert rep.has_exif is False
    assert rep.has_gps_info is False

    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not-a-valid-image-header")
    with pytest.raises(ValueError, match="Unsupported or corrupt image file"):
        inspect_image(corrupt)

    with pytest.raises(ValueError, match="output_path must be distinct"):
        strip_metadata_to_copy(png_path, png_path)


def test_strip_metadata_handles_palette_rgba_and_cmyk_conversions(tmp_path: Path) -> None:
    palette_src = tmp_path / "palette.png"
    palette_out = tmp_path / "palette_clean.png"
    rgba_src = tmp_path / "alpha.png"
    jpg_out = tmp_path / "flattened.jpg"
    cmyk_src = tmp_path / "print_cmyk.jpg"
    cmyk_png_out = tmp_path / "converted_rgb.png"

    rgb = Image.new("RGB", (16, 16), color=(20, 140, 220))
    rgb.convert("P", palette=Image.Palette.ADAPTIVE, colors=16).save(palette_src)

    strip_metadata_to_copy(palette_src, palette_out)
    with Image.open(palette_out) as clean_palette:
        assert clean_palette.convert("RGB").getpixel((0, 0)) == (20, 140, 220)

    Image.new("RGBA", (16, 16), color=(0, 128, 255, 0)).save(rgba_src)
    strip_metadata_to_copy(rgba_src, jpg_out)
    with Image.open(jpg_out) as clean_jpg:
        assert clean_jpg.format == "JPEG"
        assert clean_jpg.getpixel((0, 0)) == (255, 255, 255)

    Image.new("CMYK", (16, 16), color=(0, 50, 100, 0)).save(cmyk_src, format="JPEG")
    strip_metadata_to_copy(cmyk_src, cmyk_png_out)
    with Image.open(cmyk_png_out) as clean_cmyk_png:
        assert clean_cmyk_png.format == "PNG"
        assert clean_cmyk_png.mode == "RGB"


def test_scrub_directory_batch_skips_non_images_and_guards_overlap(tmp_path: Path) -> None:
    src_dir = tmp_path / "photos"
    out_dir = tmp_path / "scrubbed"
    src_dir.mkdir()

    img = Image.new("RGB", (20, 20), color=(40, 80, 120))
    exif = img.getexif()
    exif[271] = "LensCo"
    img.save(src_dir / "holiday.jpg", format="JPEG", exif=exif.tobytes())
    (src_dir / "notes.txt").write_text("ignore me", encoding="utf-8")

    results = scrub_directory(src_dir, out_dir)
    assert len(results) == 1
    assert results[0]["output_has_exif"] is False
    assert (out_dir / "holiday.jpg").is_file()
    assert not (out_dir / "notes.txt").exists()

    with pytest.raises(ValueError, match="separate from and outside"):
        scrub_directory(src_dir, src_dir / "nested")


def test_cli_inspect_scrub_and_batch_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "camera.jpg"
    out = tmp_path / "clean.jpg"

    img = Image.new("RGB", (24, 24), color=(15, 25, 35))
    exif = img.getexif()
    exif[271] = "CameraCorp"
    img.save(src, format="JPEG", exif=exif.tobytes())

    assert main(["inspect", str(src)]) == 0
    inspect_out = capsys.readouterr().out
    assert "CameraCorp" in inspect_out

    assert main(["scrub", str(src), str(out)]) == 0
    scrub_out = capsys.readouterr().out
    assert '"output_has_exif": false' in scrub_out


def test_recursive_scrub_directory_mirrors_nested_structure(tmp_path: Path) -> None:
    src_root = tmp_path / "library"
    nested = src_root / "2026" / "trip"
    dst_root = tmp_path / "cleaned"
    nested.mkdir(parents=True)

    img = Image.new("RGB", (18, 18), color=(90, 120, 150))
    exif = img.getexif()
    exif[271] = "NestedCam"
    img.save(nested / "frame.jpg", format="JPEG", exif=exif.tobytes())

    assert scrub_directory(src_root, dst_root, recursive=False) == []
    results = scrub_directory(src_root, dst_root, recursive=True)
    assert len(results) == 1
    assert (dst_root / "2026" / "trip" / "frame.jpg").is_file()
    assert inspect_image(dst_root / "2026" / "trip" / "frame.jpg").has_exif is False


def test_exif_orientation_transposed_upright_and_cli_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rotated_src = tmp_path / "rotated.jpg"
    upright_dst = tmp_path / "upright.jpg"

    img = Image.new("RGB", (40, 20), color=(20, 60, 140))
    exif = img.getexif()
    exif[274] = 6  # Rotate 90 CW / 270 CCW in EXIF Orientation tag
    img.save(rotated_src, format="JPEG", exif=exif.tobytes())

    strip_metadata_to_copy(rotated_src, upright_dst)
    clean_info = inspect_image(upright_dst)
    assert clean_info.has_exif is False
    assert (clean_info.width, clean_info.height) == (20, 40)

    assert main(["inspect", str(tmp_path / "nonexistent.jpg")]) == 2
    assert "error:" in capsys.readouterr().err
