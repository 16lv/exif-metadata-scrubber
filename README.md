# exif-metadata-scrubber

Image metadata inspector and non-destructive EXIF/GPS scrubber built with **Python 3.12** and **Pillow**. Inspects embedded camera/location tags and exports clean pixel copies without touching original files.

## Features

- **Structured EXIF & GPS inspection**: `inspect_image()` extracts dimensions, image format, pixel mode, decoded EXIF tags, and nested `GPSInfo` IFD (`34853`) fields while failing clearly on corrupt or unsupported inputs.
- **Pixel-buffer copy cleaning**: `strip_metadata_to_copy()` copies pixel data onto a fresh surface so auxiliary chunks (EXIF, GPS, XMP, PNG text chunks) never carry over, flattens transparent RGBA images onto white for JPEG exports, handles palette (`P`) transparency, converts `CMYK`/`YCbCr` to `RGB` for PNG/WebP/BMP, and optionally retains the ICC colour profile.
- **Safe batch folder cleanup**: `scrub_directory()` processes supported extensions in a directory, skips symlinks, and blocks overlapping source/destination folders.
- **CLI & Python API**: Works either as an importable library or via the `exif-scrubber` console script.

## Technology Stack

- Python 3.11+ (tested on Python 3.12)
- Pillow (`PIL`)
- pytest, Ruff

## Installation

```bash
pip install -e ".[dev]"
```

## Usage Examples

Inspect an image and write a scrubbed copy from the CLI:

```bash
exif-scrubber inspect photo.jpg
exif-scrubber scrub photo.jpg clean/photo.jpg --keep-icc
exif-scrubber scrub-dir raw_photos clean_photos --recursive
```

Use the Python functions directly:

```python
from pathlib import Path
from image_metadata.inspector import inspect_image, scrub_directory, strip_metadata_to_copy

report = inspect_image(Path("photo.jpg"))
print(report.has_gps_info, report.exif_fields)

strip_metadata_to_copy(Path("photo.jpg"), Path("clean/photo.jpg"))
scrub_directory(Path("raw_photos"), Path("clean_photos"))
```

## Technical Implementation Details

- Pillow stores GPS metadata inside sub-IFD tag `34853`; calling `exif_data.get_ifd(34853)` ensures nested coordinates decode rather than showing raw IFD pointer offsets.
- Re-encoding via a freshly constructed `Image.new(...)` avoids `img.copy()` accidentally preserving format-specific `.info` metadata dictionaries.

## Project Structure

```text
exif-metadata-scrubber/
├── src/image_metadata/
│   ├── __init__.py
│   └── inspector.py
├── tests/
│   └── test_inspector.py
├── pyproject.toml
└── requirements.txt
```

## Testing

```bash
ruff check .
pytest -v
```

## Known Limitations & Future Improvements

- JPEG re-encoding is lossy relative to byte-level container marker stripping; adding lossless JPEG `APPn`/`COM` segment filtering would preserve exact DCT coefficients.
- Animated multi-frame GIF/WebP inputs currently write only the first frame.
