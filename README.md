# exif-metadata-scrubber

Image inspection and metadata-stripping utility built with **Python 3.12** and **Pillow**. Reads EXIF and GPS tags from raster images and writes clean pixel copies without mutating the source file.

## Features

- **Structured EXIF inspection**: `inspect_image()` extracts dimensions, image format, decoded EXIF fields, and nested `GPSInfo` tags while rejecting corrupt or unreadable files cleanly.
- **Metadata removal on copy**: `strip_metadata_to_copy()` rebuilds pixel data on a fresh canvas without transferring `info`/EXIF dictionaries, preserving palette colours (`P` mode) and flattening alpha channels onto white when exporting `RGBA` sources to JPEG.
- **Original-file protection**: Rejects identical resolved source and destination paths before opening output files.

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

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -v
```
