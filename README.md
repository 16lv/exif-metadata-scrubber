# exif-metadata-scrubber

Image inspection and EXIF/GPS metadata removal toolkit written in **Python 3.12** and **Pillow**. Inspects embedded camera/location tags and exports clean pixel copies without changing source files.

## Features

- **Structured inspection**: `inspect_image()` extracts dimensions, image format, decoded EXIF fields, and nested `GPSInfo` tags (IFD `34853`) while rejecting corrupt images cleanly.
- **Format-safe scrubbing**: `strip_metadata_to_copy()` paints pixels onto a blank image buffer so no auxiliary metadata chunks carry over, preserving palette colours (`P` mode), flattening `RGBA` transparency onto white for JPEG output, and converting `CMYK` sources to `RGB` when exporting PNG/WebP/BMP.
- **Folder batch cleanup**: `scrub_directory()` processes supported images in a directory while skipping symlinks and blocking overlapping output folders.

## Structure

```text
exif-metadata-scrubber/
├── src/image_metadata/
│   └── inspector.py
├── tests/
│   └── test_inspector.py
├── pyproject.toml
└── requirements.txt
```

## Usage Example

```python
from pathlib import Path
from image_metadata.inspector import inspect_image, strip_metadata_to_copy, scrub_directory

report = inspect_image(Path("photo.jpg"))
print(report.has_gps_info, report.exif_fields)

strip_metadata_to_copy(Path("photo.jpg"), Path("clean/photo.jpg"))
scrub_directory(Path("raw_photos"), Path("clean_photos"))
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -v
```
