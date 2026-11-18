from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

GPS_TAG_ID = 34853
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class ImageInspectionReport:
    file_path: str
    file_size_bytes: int
    format: str
    mode: str
    width: int
    height: int
    has_exif: bool
    exif_fields: dict[str, str]
    has_gps_info: bool
    gps_summary: dict[str, str]


def inspect_image(path: Path) -> ImageInspectionReport:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    size_bytes = path.stat().st_size
    try:
        with Image.open(path) as img:
            img_format = img.format or "UNKNOWN"
            mode = img.mode
            width, height = img.size

            exif_data = img.getexif()
            exif_fields: dict[str, str] = {}
            gps_summary: dict[str, str] = {}

            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = str(ExifTags.TAGS.get(tag_id, tag_id))
                    if tag_id == GPS_TAG_ID:
                        continue
                    exif_fields[tag_name] = str(value)

                gps_ifd = exif_data.get_ifd(GPS_TAG_ID)
                if gps_ifd:
                    for gps_id, gps_val in gps_ifd.items():
                        gps_name = str(ExifTags.GPSTAGS.get(gps_id, gps_id))
                        gps_summary[gps_name] = str(gps_val)

            return ImageInspectionReport(
                file_path=str(path),
                file_size_bytes=size_bytes,
                format=img_format,
                mode=mode,
                width=width,
                height=height,
                has_exif=bool(exif_fields or gps_summary),
                exif_fields=exif_fields,
                has_gps_info=bool(gps_summary),
                gps_summary=gps_summary,
            )
    except UnidentifiedImageError as exc:
        raise ValueError(f"Unsupported or corrupt image file: {path}") from exc


def strip_metadata_to_copy(source_path: Path, output_path: Path) -> dict[str, Any]:
    source = Path(source_path)
    target = Path(output_path)
    if source.resolve() == target.resolve():
        raise ValueError(
            "output_path must be distinct from source_path to preserve the original image"
        )

    before = inspect_image(source)
    target.parent.mkdir(parents=True, exist_ok=True)

    ext_format_map = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }

    with Image.open(source) as img:
        target_format = ext_format_map.get(target.suffix.lower(), img.format or "JPEG")

        # Palette ("P") images must be converted so indexed colours are preserved
        if img.mode == "P":
            has_transparency = "transparency" in img.info
            pixel_source = img.convert("RGBA" if has_transparency else "RGB")
        else:
            pixel_source = Image.new(img.mode, img.size)
            pixel_source.paste(img)

        if target_format == "JPEG" and pixel_source.mode in ("RGBA", "LA", "PA"):
            rgba = pixel_source.convert("RGBA")
            flattened = Image.new("RGB", rgba.size, (255, 255, 255))
            flattened.paste(rgba, mask=rgba.split()[3])
            clean_img = flattened
        elif (
            (target_format == "JPEG" and pixel_source.mode not in ("RGB", "L", "CMYK"))
            or (
                target_format in ("PNG", "WEBP", "BMP")
                and pixel_source.mode not in ("RGB", "RGBA", "L", "LA")
            )
        ):
            clean_img = pixel_source.convert("RGB")
        else:
            clean_img = pixel_source

        clean_img.save(target, format=target_format)

    after = inspect_image(target)
    return {
        "source_path": str(source),
        "output_path": str(target),
        "removed_exif_field_count": len(before.exif_fields),
        "removed_gps_data": before.has_gps_info,
        "output_has_exif": after.has_exif,
    }


def scrub_directory(source_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    src_root = Path(source_dir)
    dst_root = Path(output_dir)
    if not src_root.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {src_root}")
    if src_root.resolve() == dst_root.resolve() or src_root.resolve() in dst_root.resolve().parents:
        raise ValueError("output_dir must be separate from and outside source_dir")

    results: list[dict[str, Any]] = []
    for entry in sorted(src_root.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        results.append(strip_metadata_to_copy(entry, dst_root / entry.name))
    return results
