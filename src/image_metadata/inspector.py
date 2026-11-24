from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

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


def strip_metadata_to_copy(
    source_path: Path,
    output_path: Path,
    keep_icc_profile: bool = False,
) -> dict[str, Any]:
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

    with Image.open(source) as raw_img:
        target_format = ext_format_map.get(target.suffix.lower(), raw_img.format or "JPEG")
        icc_profile = raw_img.info.get("icc_profile") if keep_icc_profile else None
        img = ImageOps.exif_transpose(raw_img)
        try:
            if img.mode == "P":
                has_transparency = "transparency" in img.info
                pixel_source = img.convert("RGBA" if has_transparency else "RGB")
            else:
                pixel_source = Image.new(img.mode, img.size)
                pixel_source.paste(img)
        finally:
            if img is not raw_img:
                img.close()

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

        save_kwargs: dict[str, Any] = {"format": target_format}
        if icc_profile and target_format != "BMP":
            save_kwargs["icc_profile"] = icc_profile
        clean_img.save(target, **save_kwargs)

    after = inspect_image(target)
    return {
        "source_path": str(source),
        "output_path": str(target),
        "removed_exif_field_count": len(before.exif_fields),
        "removed_gps_data": before.has_gps_info,
        "output_has_exif": after.has_exif,
    }


def scrub_directory(
    source_dir: Path,
    output_dir: Path,
    keep_icc_profile: bool = False,
    recursive: bool = False,
) -> list[dict[str, Any]]:
    src_root = Path(source_dir)
    dst_root = Path(output_dir)
    if not src_root.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {src_root}")
    if src_root.resolve() == dst_root.resolve() or src_root.resolve() in dst_root.resolve().parents:
        raise ValueError("output_dir must be separate from and outside source_dir")

    candidates = sorted(src_root.rglob("*") if recursive else src_root.iterdir())
    results: list[dict[str, Any]] = []
    for entry in candidates:
        if entry.is_symlink() or not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel_path = entry.relative_to(src_root)
        results.append(
            strip_metadata_to_copy(entry, dst_root / rel_path, keep_icc_profile=keep_icc_profile)
        )
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect image EXIF/GPS metadata and write clean pixel copies."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inspect", help="Inspect metadata in a single image file")
    inspect_cmd.add_argument("image", type=Path)

    scrub_cmd = sub.add_parser("scrub", help="Strip metadata from a single image into a new copy")
    scrub_cmd.add_argument("source", type=Path)
    scrub_cmd.add_argument("output", type=Path)
    scrub_cmd.add_argument("--keep-icc", action="store_true", help="Retain embedded ICC profile")

    dir_cmd = sub.add_parser("scrub-dir", help="Strip metadata from supported images in a folder")
    dir_cmd.add_argument("source_dir", type=Path)
    dir_cmd.add_argument("output_dir", type=Path)
    dir_cmd.add_argument("--keep-icc", action="store_true", help="Retain embedded ICC profile")
    dir_cmd.add_argument(
        "--recursive",
        action="store_true",
        help="Traverse subdirectories and mirror structure under output_dir",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(asdict(inspect_image(args.image)), indent=2))
        elif args.command == "scrub":
            summary = strip_metadata_to_copy(args.source, args.output, keep_icc_profile=args.keep_icc)
            print(json.dumps(summary, indent=2))
        elif args.command == "scrub-dir":
            results = scrub_directory(
                args.source_dir,
                args.output_dir,
                keep_icc_profile=args.keep_icc,
                recursive=args.recursive,
            )
            print(json.dumps({"processed": len(results), "files": results}, indent=2))
        return 0
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, ValueError, UnidentifiedImageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
