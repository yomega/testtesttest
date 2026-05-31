from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from docx import Document as DocxDocument

from .models import ExtractedSegment, ExtractedTable, ExtractionOptions, ManualTableRegion, PagePreviewImage, SourceDocument


def _runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


PROJECT_RUNTIME_DIR = _runtime_base_dir() / ".runtime"
WINDOWS_TESSERACT_DIR = Path(r"C:\Program Files\Tesseract-OCR")
EVALUATION_WARNING_PREFIX = "Evaluation Warning"
SPIRE_EVALUATION_WARNING_TEXT = "the document was created with spire.pdf for python"
POWER_QUERY_TIMEOUT_SECONDS = 90.0
PDFPLUMBER_DEBUG_IMAGE_RESOLUTION = 110
ProgressCallback = Callable[[float, str], None]
POWER_QUERY_RUNTIME_DIR = PROJECT_RUNTIME_DIR / "power_query_sdk"
POWER_QUERY_BOOTSTRAP_NAME = "PdfSpecBootstrap"


def _append_raw_import_text(existing: str, addition: str) -> str:
    if not addition:
        return existing
    if not existing:
        return addition
    return f"{existing}\n{addition}"


def _configure_runtime_environment() -> None:
    PROJECT_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if WINDOWS_TESSERACT_DIR.exists():
        current_path = os.environ.get("PATH", "")
        tesseract_path = str(WINDOWS_TESSERACT_DIR)
        if tesseract_path.lower() not in current_path.lower():
            os.environ["PATH"] = f"{tesseract_path}{os.pathsep}{current_path}" if current_path else tesseract_path
        os.environ.setdefault("TESSDATA_PREFIX", str(WINDOWS_TESSERACT_DIR / "tessdata"))


_configure_runtime_environment()

try:
    spire_pdf = importlib.import_module("spire.pdf")
except ImportError:  # pragma: no cover - dependency may not be installed in the workspace
    spire_pdf = None

try:
    spire_pdf_common = importlib.import_module("spire.pdf.common")
except ImportError:  # pragma: no cover - dependency may not be installed in the workspace
    spire_pdf_common = None

try:
    import pypdfium2
except ImportError:  # pragma: no cover - dependency may not be installed in the workspace
    pypdfium2 = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - dependency may not be installed in the workspace
    pytesseract = None

try:
    import pdfplumber
except ImportError:  # pragma: no cover - dependency may not be installed in the workspace
    pdfplumber = None

class ExtractionError(RuntimeError):
    """Raised when a document cannot be processed."""


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"th", "td"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._in_cell:
            value = "".join(self._current_cell).strip()
            self._current_row.append(value)
            self._current_cell = []
            self._in_cell = False
        elif tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def _table_from_html(html: str | None) -> tuple[list[str], list[list[str]]]:
    if not html:
        return [], []

    parser = _HtmlTableParser()
    parser.feed(html)
    rows = [row for row in parser.rows if any(cell.strip() for cell in row)]
    if not rows:
        return [], []

    headers = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    return headers, body


def _split_evaluation_warnings(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            kept_lines.append(raw_line)
            continue
        if line.startswith(EVALUATION_WARNING_PREFIX):
            if SPIRE_EVALUATION_WARNING_TEXT in line.casefold():
                continue
            if line not in warnings:
                warnings.append(line)
            continue
        kept_lines.append(raw_line)
    cleaned_text = "\n".join(line for line in kept_lines).strip()
    return cleaned_text, warnings


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _is_header_like_cell(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    if normalized.startswith("$"):
        return False
    if re.search(r"\d", normalized):
        return False
    return bool(re.search(r"[A-Za-z]", normalized))


def _looks_like_new_header_row(current_block: list[list[str]], cells: list[str]) -> bool:
    if len(current_block) < 2:
        return False

    if not cells or sum(1 for cell in cells if _is_header_like_cell(cell)) < max(2, len(cells) - 1):
        return False

    prior_rows = current_block[1:] if len(current_block) > 1 else current_block
    if not prior_rows:
        return False

    prior_data_like_cells = sum(
        1
        for row in prior_rows
        for cell in row
        if cell.strip() and (cell.startswith("$") or bool(re.search(r"\d", cell)))
    )
    return prior_data_like_cells > 0


def _infer_tables_from_text(page_number: int, text: str) -> list[ExtractedTable]:
    blocks: list[list[list[str]]] = []
    current_block: list[list[str]] = []
    current_width: int | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if len(current_block) >= 2:
                blocks.append(current_block)
            current_block = []
            current_width = None
            continue

        cells = [part.strip() for part in re.split(r"\t+|\s{2,}", line) if part.strip()]
        if len(cells) < 2:
            if len(current_block) >= 2:
                blocks.append(current_block)
            current_block = []
            current_width = None
            continue

        width = len(cells)
        if current_width is None or width == current_width:
            current_block.append(cells)
            current_width = width
            continue

        if _looks_like_new_header_row(current_block, cells):
            if len(current_block) >= 2:
                blocks.append(current_block)
            current_block = [cells]
            current_width = width
            continue

        if current_block and current_width is not None:
            # Once we have an inferred table, keep subsequent rows attached unless
            # we hit an explicit boundary. Missing blank cells often make later rows
            # appear narrower, and schema reflow can repair that.
            current_block.append(cells)
            continue

        if len(current_block) >= 2:
            blocks.append(current_block)
        current_block = [cells]
        current_width = width

    if len(current_block) >= 2:
        blocks.append(current_block)

    tables: list[ExtractedTable] = []
    for rows in blocks:
        headers = rows[0]
        body = rows[1:]
        if not body:
            continue
        raw_text = "\n".join(" | ".join(cell for cell in row) for row in rows)
        tables.append(
            ExtractedTable(
                page_number=page_number,
                headers=headers,
                rows=body,
                import_headers=list(headers),
                source_text=text,
                raw_text=raw_text,
                confidence=0.45,
                backend="text_fallback",
            )
        )
    return tables


def _page_number_from_table_name(name: str) -> int:
    patterns = (
        r"Page\D*(\d+)",
        r"P(?:age)?[_\s-]*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 1


def _normalize_power_query_table(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    if headers and all(re.fullmatch(r"Column\d+", header or "", re.IGNORECASE) for header in headers) and rows:
        return rows[0], rows[1:]
    return headers, rows


def _normalize_extracted_rows(rows: list[list[Any]]) -> list[list[str]]:
    return [
        ["" if cell is None else str(cell).strip() for cell in row]
        for row in rows
        if row and any(str(cell or "").strip() for cell in row)
    ]


def _pdfplumber_table_settings(options: ExtractionOptions) -> dict[str, Any] | None:
    if options.pdfplumber_use_default_table_settings:
        return None
    settings: dict[str, Any] = {
        "vertical_strategy": options.pdfplumber_vertical_strategy,
        "horizontal_strategy": options.pdfplumber_horizontal_strategy,
        "snap_tolerance": 4,
        "join_tolerance": 4,
        "intersection_tolerance": 4,
        "text_tolerance": 3,
    }
    if options.pdfplumber_vertical_strategy == "text":
        settings["min_words_vertical"] = 1
        settings["text_x_tolerance"] = options.pdfplumber_text_x_tolerance
    if options.pdfplumber_horizontal_strategy == "text":
        settings["min_words_horizontal"] = 1
        settings["text_y_tolerance"] = options.pdfplumber_text_y_tolerance
    return settings


def _pdfplumber_page_pixel_size(page: Any, resolution: int = PDFPLUMBER_DEBUG_IMAGE_RESOLUTION) -> tuple[int, int]:
    width_points = float(getattr(page, "width", 0.0) or 0.0)
    height_points = float(getattr(page, "height", 0.0) or 0.0)
    scale = resolution / 72.0
    return max(1, round(width_points * scale)), max(1, round(height_points * scale))


def _group_manual_table_regions_by_page(
    regions: list[ManualTableRegion],
) -> dict[int, list[ManualTableRegion]]:
    grouped: dict[int, list[ManualTableRegion]] = {}
    for region in regions:
        grouped.setdefault(region.page_number, []).append(region)
    return grouped


def _decode_pqtest_text_output(raw_output: str) -> str:
    text = raw_output.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].replace('""', '"')
    return text


def _sdk_extension_root() -> Path:
    return Path(os.environ.get("USERPROFILE", "")) / ".vscode" / "extensions"


def _tool_launch_env(tool_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    tool_dir = str(tool_path.parent)
    current_path = env.get("PATH", "")
    env["PATH"] = f"{tool_dir}{os.pathsep}{current_path}" if current_path else tool_dir
    return env


class DocumentExtractor:
    """Extracts local document content using Spire.PDF for PDFs."""

    def extract(
        self,
        file_path: str | Path,
        options: ExtractionOptions | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> SourceDocument:
        self._report(progress_callback, 5.0, "Preparing extraction...")
        options = options or ExtractionOptions()
        path = Path(file_path)
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf(path, options, progress_callback)
        if suffix == ".docx":
            self._report(progress_callback, 15.0, "Reading DOCX document...")
            return self._extract_docx(path)
        if suffix == ".doc":
            raise ExtractionError("Legacy .doc extraction is not supported in the current local-only build.")
        self._report(progress_callback, 25.0, "Reading plain text document...")
        return self._extract_text(path)

    def generate_pdfplumber_debug_images(
        self,
        file_path: str | Path,
        options: ExtractionOptions | None = None,
    ) -> list[tuple[int, bytes]]:
        options = options or ExtractionOptions()
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return []
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        debug_images: list[tuple[int, bytes]] = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    debug_png = self._capture_pdfplumber_debug_tablefinder(page, options)
                    if debug_png is not None:
                        debug_images.append((page_index + 1, debug_png))
        except Exception as exc:  # pragma: no cover - dependency/runtime-specific failures
            raise ExtractionError(
                f"pdfplumber could not generate tablefinder debug images for this PDF: {path.name}. Details: {exc}"
            ) from exc

        return debug_images

    @staticmethod
    def describe_pdfplumber_table_settings(options: ExtractionOptions) -> str:
        return (
            "[pdfplumber defaults]"
            if options.pdfplumber_use_default_table_settings
            else json.dumps(_pdfplumber_table_settings(options), sort_keys=True)
        )

    def generate_pdf_page_previews(
        self,
        file_path: str | Path,
        resolution: int = PDFPLUMBER_DEBUG_IMAGE_RESOLUTION,
    ) -> list[PagePreviewImage]:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return []
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        previews: list[PagePreviewImage] = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    preview = self._render_pdfplumber_page_preview(page, page_index + 1, resolution)
                    if preview is not None:
                        previews.append(preview)
        except Exception as exc:  # pragma: no cover - dependency/runtime-specific failures
            raise ExtractionError(f"pdfplumber could not render page previews for this PDF: {path.name}. Details: {exc}") from exc

        return previews

    def _extract_pdf(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> SourceDocument:
        if options.ocr_backend == "tesseract_only":
            return self._extract_pdf_with_ocr_only(path, options, progress_callback)

        if options.table_extraction_backend == "pdfplumber":
            return self._extract_pdf_with_pdfplumber(path, options, progress_callback)

        if spire_pdf is None:
            raise ExtractionError("Spire.PDF is not installed. Install project dependencies first.")

        self._report(progress_callback, 15.0, "Running Spire.PDF extraction...")

        pdf_document = self._create_spire_document(path)
        table_extractor = None
        source_document = SourceDocument(
            path=path,
            title=path.stem,
            extraction_debug={
                "pdf_backend": "spire",
                "extract_tables": str(options.extract_tables),
                "table_backend": options.table_extraction_backend,
                "ocr_backend": options.ocr_backend,
                "ocr_language": options.ocr_language,
            },
        )

        try:
            page_total = self._get_page_count(pdf_document)
            missing_text_pages: list[int] = []
            evaluation_warnings: list[str] = []
            page_text_by_number: dict[int, str] = {}

            for page_index in range(page_total):
                page_number = page_index + 1
                page = self._get_spire_page(pdf_document, page_index)
                raw_page_text = self._extract_spire_page_text(page)
                source_document.raw_import_text = _append_raw_import_text(source_document.raw_import_text, raw_page_text)
                page_text, page_warnings = _split_evaluation_warnings(raw_page_text)
                evaluation_warnings.extend(page_warnings)
                page_text_by_number[page_number] = page_text
                if page_text:
                    source_document.segments.append(
                        ExtractedSegment(
                            page_number=page_number,
                            text=page_text,
                            confidence=0.92,
                            segment_type="pdf_text",
                        )
                    )
                else:
                    missing_text_pages.append(page_index)

                progress = 20.0 + (50.0 * page_number / max(page_total, 1))
                self._report(progress_callback, progress, "Extracting PDF pages with Spire.PDF...")

            if options.extract_tables:
                self._report(progress_callback, 72.0, "Extracting tables from PDF...")
                if options.table_extraction_backend == "power_query":
                    power_query_failed = False
                    try:
                        power_query_tables = self._extract_power_query_tables(
                            path,
                            evaluation_warnings,
                            progress_callback,
                        )
                    except ExtractionError as exc:
                        power_query_failed = True
                        evaluation_warnings.append(
                            "Power Query Pdf.Tables() failed and the app fell back to local extraction. "
                            f"Details: {exc}"
                        )
                        power_query_tables = []

                    if power_query_tables:
                        source_document.tables.extend(power_query_tables)
                    else:
                        if not power_query_failed:
                            evaluation_warnings.append(
                                "Power Query Pdf.Tables() returned no usable tables. Falling back to local extraction."
                            )
                        table_extractor = self._create_table_extractor(pdf_document)
                        self._extract_local_table_fallbacks(
                            source_document,
                            table_extractor,
                            page_total,
                            page_text_by_number,
                            evaluation_warnings,
                        )
                else:
                    table_extractor = self._create_table_extractor(pdf_document)
                    self._extract_local_table_fallbacks(
                        source_document,
                        table_extractor,
                        page_total,
                        page_text_by_number,
                        evaluation_warnings,
                    )

            if missing_text_pages:
                self._report(progress_callback, 75.0, f"Running {options.ocr_backend} OCR on image-only PDF pages...")
                ocr_segments = self._extract_pdf_pages_with_local_ocr(
                    path,
                    missing_text_pages,
                    options.ocr_backend,
                    options.ocr_language,
                    progress_callback,
                )
                source_document.segments.extend(ocr_segments)
                for segment in ocr_segments:
                    source_document.raw_import_text = _append_raw_import_text(source_document.raw_import_text, segment.text)

            source_document.segments.sort(key=lambda segment: segment.page_number)
            source_document.evaluation_warnings = _dedupe_preserve_order(evaluation_warnings)
        finally:
            if table_extractor is not None:
                self._safe_spire_dispose(table_extractor)
            self._safe_spire_dispose(pdf_document)

        if not source_document.segments and not source_document.tables:
            source_document.segments.append(
                ExtractedSegment(
                    page_number=1,
                    text="[No content extracted. Verify the PDF is text-based or that local OCR is configured.]",
                    confidence=0.0,
                    segment_type="extraction_gap",
                )
            )

        self._report(progress_callback, 78.0, "Organizing extracted PDF content...")
        return source_document

    def _extract_pdf_with_pdfplumber(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> SourceDocument:
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        self._report(progress_callback, 15.0, "Running pdfplumber extraction...")
        source_document = SourceDocument(
            path=path,
            title=path.stem,
            extraction_debug={
                "pdf_backend": "pdfplumber",
                "extract_tables": str(options.extract_tables),
                "table_backend": options.table_extraction_backend,
                "ocr_backend": options.ocr_backend,
                "ocr_language": options.ocr_language,
                "pdfplumber_use_default_table_settings": str(options.pdfplumber_use_default_table_settings),
                "pdfplumber_vertical_strategy": options.pdfplumber_vertical_strategy,
                "pdfplumber_horizontal_strategy": options.pdfplumber_horizontal_strategy,
                "pdfplumber_text_x_tolerance": str(options.pdfplumber_text_x_tolerance),
                "pdfplumber_text_y_tolerance": str(options.pdfplumber_text_y_tolerance),
                "pdfplumber_table_settings": (
                    "[pdfplumber defaults]"
                    if options.pdfplumber_use_default_table_settings
                    else json.dumps(_pdfplumber_table_settings(options), sort_keys=True)
                ),
            },
        )
        missing_text_pages: list[int] = []
        max_page_width_px = 0
        max_page_height_px = 0
        manual_regions_by_page = _group_manual_table_regions_by_page(options.manual_table_regions)

        try:
            with pdfplumber.open(str(path)) as pdf:
                page_total = len(pdf.pages)
                for page_index, page in enumerate(pdf.pages):
                    page_number = page_index + 1
                    page_width_px, page_height_px = _pdfplumber_page_pixel_size(page)
                    max_page_width_px = max(max_page_width_px, page_width_px)
                    max_page_height_px = max(max_page_height_px, page_height_px)
                    preview = self._render_pdfplumber_page_preview(page, page_number)
                    if preview is not None:
                        source_document.page_preview_images.append(preview)
                    raw_page_text = page.extract_text() or ""
                    source_document.raw_import_text = _append_raw_import_text(source_document.raw_import_text, raw_page_text)
                    if raw_page_text.strip():
                        source_document.segments.append(
                            ExtractedSegment(
                                page_number=page_number,
                                text=raw_page_text,
                                confidence=0.9,
                                segment_type="pdf_text",
                            )
                        )
                    else:
                        missing_text_pages.append(page_index)

                    debug_png = self._capture_pdfplumber_debug_tablefinder(page, options)
                    if debug_png is not None:
                        source_document.pdfplumber_debug_images.append((page_number, debug_png))

                    if options.extract_tables:
                        page_regions = manual_regions_by_page.get(page_number, [])
                        page_tables: list[ExtractedTable] = []
                        if page_regions:
                            page_tables.extend(
                                self._extract_pdfplumber_tables_from_regions(
                                    page,
                                    page_number,
                                    raw_page_text,
                                    options,
                                    page_regions,
                                )
                            )
                        elif not page_tables:
                            page_tables.extend(
                                self._build_pdfplumber_tables_from_rows(
                                    self._extract_pdfplumber_tables_from_page(page, options),
                                    page_number,
                                    raw_page_text,
                                    backend="pdfplumber",
                                )
                            )
                        source_document.tables.extend(page_tables)

                    progress = 20.0 + (50.0 * page_number / max(page_total, 1))
                    self._report(progress_callback, progress, "Extracting PDF pages with pdfplumber...")
        except Exception as exc:  # pragma: no cover - dependency/runtime-specific failures
            raise ExtractionError(f"pdfplumber could not open or extract this PDF: {path.name}. Details: {exc}") from exc

        source_document.extraction_debug["pdfplumber_max_page_width_px"] = str(max_page_width_px or 1)
        source_document.extraction_debug["pdfplumber_max_page_height_px"] = str(max_page_height_px or 1)
        source_document.extraction_debug["manual_table_regions"] = str(len(options.manual_table_regions))

        if options.extract_tables and not source_document.tables:
            for segment in source_document.segments:
                if segment.text:
                    source_document.tables.extend(_infer_tables_from_text(segment.page_number, segment.text))

        if missing_text_pages:
            self._report(progress_callback, 75.0, f"Running {options.ocr_backend} OCR on image-only PDF pages...")
            ocr_segments = self._extract_pdf_pages_with_local_ocr(
                path,
                missing_text_pages,
                options.ocr_backend,
                options.ocr_language,
                progress_callback,
            )
            source_document.segments.extend(ocr_segments)
            for segment in ocr_segments:
                source_document.raw_import_text = _append_raw_import_text(source_document.raw_import_text, segment.text)

        source_document.segments.sort(key=lambda segment: segment.page_number)

        if not source_document.segments and not source_document.tables:
            source_document.segments.append(
                ExtractedSegment(
                    page_number=1,
                    text="[No content extracted. Verify the PDF is text-based or that local OCR is configured.]",
                    confidence=0.0,
                    segment_type="extraction_gap",
                )
            )

        self._report(progress_callback, 78.0, "Organizing extracted PDF content...")
        return source_document

    def _capture_pdfplumber_debug_tablefinder(self, page: Any, options: ExtractionOptions) -> bytes | None:
        table_settings = _pdfplumber_table_settings(options)
        try:
            page_image = page.to_image(resolution=PDFPLUMBER_DEBUG_IMAGE_RESOLUTION)
            debug_image = page_image.debug_tablefinder() if table_settings is None else page_image.debug_tablefinder(table_settings)
            return debug_image._repr_png_()
        except Exception:
            return None

    def _render_pdfplumber_page_preview(
        self,
        page: Any,
        page_number: int,
        resolution: int = PDFPLUMBER_DEBUG_IMAGE_RESOLUTION,
    ) -> PagePreviewImage | None:
        try:
            page_image = page.to_image(resolution=resolution)
            image_bytes = page_image._repr_png_()
            if not image_bytes:
                return None
            image_width_px, image_height_px = _pdfplumber_page_pixel_size(page, resolution)
            return PagePreviewImage(
                page_number=page_number,
                image_bytes=image_bytes,
                image_width_px=image_width_px,
                image_height_px=image_height_px,
                page_width_pts=float(getattr(page, "width", 0.0) or 0.0),
                page_height_pts=float(getattr(page, "height", 0.0) or 0.0),
            )
        except Exception:
            return None

    def _build_pdfplumber_tables_from_rows(
        self,
        extracted_tables: list[list[list[Any]]],
        page_number: int,
        source_text: str,
        backend: str,
    ) -> list[ExtractedTable]:
        built_tables: list[ExtractedTable] = []
        for extracted_rows in extracted_tables:
            rows = _normalize_extracted_rows(extracted_rows)
            if len(rows) < 2:
                continue
            headers = rows[0]
            body = rows[1:]
            raw_text = "\n".join(" | ".join(cell for cell in row) for row in rows)
            built_tables.append(
                ExtractedTable(
                    page_number=page_number,
                    headers=headers,
                    rows=body,
                    import_headers=list(headers),
                    source_text=source_text,
                    raw_text=raw_text,
                    confidence=0.82,
                    backend=backend,
                )
            )
        return built_tables

    def _extract_pdfplumber_tables_from_regions(
        self,
        page: Any,
        page_number: int,
        page_source_text: str,
        options: ExtractionOptions,
        regions: list[ManualTableRegion],
    ) -> list[ExtractedTable]:
        region_tables: list[ExtractedTable] = []
        for index, region in enumerate(regions, start=1):
            bbox = (
                min(region.left, region.right),
                min(region.top, region.bottom),
                max(region.left, region.right),
                max(region.top, region.bottom),
            )
            try:
                cropped_page = page.crop(bbox)
            except Exception:
                continue
            cropped_text = cropped_page.extract_text() or page_source_text
            extracted_tables = self._extract_pdfplumber_tables_from_page(cropped_page, options)
            built_tables = self._build_pdfplumber_tables_from_rows(
                extracted_tables,
                page_number,
                cropped_text,
                backend="pdfplumber_region",
            )
            if not built_tables and cropped_text:
                built_tables = _infer_tables_from_text(page_number, cropped_text)
                for table in built_tables:
                    table.backend = "pdfplumber_region_text_fallback"
            label = region.label or f"region {index}"
            for table in built_tables:
                table.raw_text = table.raw_text or cropped_text
                table.schema_debug_notes.append(f"Extracted from manual region: {label}")
            region_tables.extend(built_tables)
        return region_tables

    def _extract_pdf_with_ocr_only(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> SourceDocument:
        self._report(progress_callback, 15.0, "Running Tesseract OCR-only extraction...")
        source_document = SourceDocument(
            path=path,
            title=path.stem,
            extraction_debug={
                "pdf_backend": "ocr_only",
                "extract_tables": str(options.extract_tables),
                "table_backend": options.table_extraction_backend,
                "ocr_backend": "tesseract",
                "ocr_language": options.ocr_language,
            },
        )
        source_document.evaluation_warnings.append(
            "OCR-only mode was used. Spire.PDF text extraction and Power Query Pdf.Tables() were not used for this run."
        )
        ocr_segments = self._extract_pdf_pages_with_local_ocr(
            path,
            None,
            "tesseract",
            options.ocr_language,
            progress_callback,
        )
        source_document.segments.extend(ocr_segments)
        source_document.segments.sort(key=lambda segment: segment.page_number)
        source_document.raw_import_text = "\n".join(segment.text for segment in ocr_segments if segment.text)

        if options.extract_tables:
            for segment in source_document.segments:
                if segment.text and segment.segment_type == "ocr_page_text":
                    source_document.tables.extend(_infer_tables_from_text(segment.page_number, segment.text))

        if not source_document.segments and not source_document.tables:
            source_document.segments.append(
                ExtractedSegment(
                    page_number=1,
                    text="[No content extracted. Verify local OCR is configured.]",
                    confidence=0.0,
                    segment_type="extraction_gap",
                )
            )

        self._report(progress_callback, 78.0, "Organizing OCR-only PDF content...")
        return source_document

    def _extract_pdfplumber_tables_from_page(self, page: Any, options: ExtractionOptions) -> list[list[list[Any]]]:
        collected_tables: list[list[list[Any]]] = []
        seen_signatures: set[str] = set()
        table_settings = _pdfplumber_table_settings(options)

        if table_settings is None:
            try:
                extracted_tables = page.extract_tables() or []
            except Exception:
                extracted_tables = []
        else:
            try:
                extracted_tables = page.extract_tables(table_settings=table_settings) or []
            except TypeError:
                extracted_tables = page.extract_tables(table_settings) or []
            except Exception:
                extracted_tables = []

        if not extracted_tables:
            if table_settings is None:
                try:
                    found_tables = page.find_tables() or []
                except Exception:
                    found_tables = []
            else:
                try:
                    found_tables = page.find_tables(table_settings=table_settings) or []
                except TypeError:
                    found_tables = page.find_tables(table_settings) or []
                except Exception:
                    found_tables = []
            extracted_tables = [table.extract(**((table_settings or {}).get("text_settings") or {})) for table in found_tables]

        for extracted_rows in extracted_tables:
            normalized_rows = _normalize_extracted_rows(extracted_rows)
            if len(normalized_rows) < 2:
                continue
            signature = "\n".join(" | ".join(row) for row in normalized_rows)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            collected_tables.append(extracted_rows)

        return collected_tables

    def _create_spire_document(self, path: Path) -> Any:
        try:
            pdf_document = self._spire_attr("PdfDocument")()
            pdf_document.LoadFromFile(str(path))
            return pdf_document
        except Exception as exc:  # pragma: no cover - dependency-specific failures
            raise ExtractionError(f"Spire.PDF could not open this PDF: {path.name}. Details: {exc}") from exc

    def _create_table_extractor(self, pdf_document: Any) -> Any | None:
        try:
            return self._spire_attr("PdfTableExtractor")(pdf_document)
        except Exception as exc:  # pragma: no cover - dependency-specific failures
            raise ExtractionError(f"Spire.PDF could not initialize table extraction. Details: {exc}") from exc

    def _extract_spire_page_text(self, page: Any) -> str:
        text_extractor = self._spire_attr("PdfTextExtractor")(page)
        extract_options = self._spire_attr("PdfTextExtractOptions")()
        if hasattr(extract_options, "IsExtractAllText"):
            extract_options.IsExtractAllText = True
        if hasattr(extract_options, "IsShowHiddenText"):
            extract_options.IsShowHiddenText = False
        return (text_extractor.ExtractText(extract_options) or "").strip()

    def _extract_spire_tables(
        self,
        table_extractor: Any,
        page_index: int,
        page_number: int,
        evaluation_warnings: list[str],
    ) -> list[ExtractedTable]:
        try:
            raw_tables = table_extractor.ExtractTable(page_index) or []
        except Exception as exc:  # pragma: no cover - dependency-specific failures
            raise ExtractionError(
                f"Spire.PDF table extraction failed on page {page_index + 1}. Details: {exc}"
            ) from exc

        extracted_tables: list[ExtractedTable] = []
        for raw_table in raw_tables:
            row_count = raw_table.GetRowCount()
            column_count = raw_table.GetColumnCount()
            rows: list[list[str]] = []

            for row_index in range(row_count):
                row_cells: list[str] = []
                for column_index in range(column_count):
                    cell_text, cell_warnings = _split_evaluation_warnings(raw_table.GetText(row_index, column_index) or "")
                    evaluation_warnings.extend(cell_warnings)
                    row_cells.append(cell_text.replace("\n", " ").strip())
                rows.append(row_cells)

            rows = [row for row in rows if any(cell for cell in row)]
            if not rows:
                continue

            headers = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            raw_text = "\n".join(" | ".join(cell for cell in row) for row in rows if any(cell for cell in row))
            if not raw_text.strip():
                continue
            extracted_tables.append(
                ExtractedTable(
                    page_number=page_number,
                    headers=headers,
                    rows=body,
                    import_headers=list(headers),
                    source_text="",
                    raw_text=raw_text,
                    confidence=0.88,
                    backend="spire",
                )
            )

        return extracted_tables

    def _extract_local_table_fallbacks(
        self,
        source_document: SourceDocument,
        table_extractor: Any,
        page_total: int,
        page_text_by_number: dict[int, str],
        evaluation_warnings: list[str],
    ) -> None:
        for page_index in range(page_total):
            page_number = page_index + 1
            page_text = page_text_by_number.get(page_number, "")
            page_tables = self._extract_spire_tables(table_extractor, page_index, page_number, evaluation_warnings)
            if page_tables:
                for table in page_tables:
                    if page_text:
                        table.source_text = page_text
                    elif not table.source_text:
                        table.source_text = table.raw_text
                source_document.tables.extend(page_tables)
            elif page_text:
                source_document.tables.extend(_infer_tables_from_text(page_number, page_text))

    def _extract_power_query_tables(
        self,
        path: Path,
        evaluation_warnings: list[str],
        progress_callback: ProgressCallback | None = None,
    ) -> list[ExtractedTable]:
        pqtest_path = self._resolve_pqtest_path()
        extension_path = self._ensure_power_query_bootstrap_extension()
        runtime_dir = POWER_QUERY_RUNTIME_DIR / uuid.uuid4().hex
        runtime_dir.mkdir(parents=True, exist_ok=True)
        query_path = runtime_dir / "pdf_tables.query.pq"
        output_path = runtime_dir / "pdf_tables.query.pqout"
        try:
            self._report(progress_callback, 73.0, "Preparing Power Query SDK extraction...")
            query_path.write_text(self._build_power_query_formula(path), encoding="utf-8")

            self._report(progress_callback, 74.0, "Running PQTest.exe against Pdf.Tables()...")
            completed = subprocess.run(
                [str(pqtest_path), "run-compare", "-e", str(extension_path), "-q", str(query_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(pqtest_path.parent),
                env=_tool_launch_env(pqtest_path),
                timeout=POWER_QUERY_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or f"Exit code {completed.returncode}"
                raise ExtractionError(f"PQTest.exe failed while evaluating Pdf.Tables(). Details: {detail}")

            if not output_path.exists():
                raise ExtractionError("PQTest.exe completed but no .pqout file was generated for the Pdf.Tables() query.")

            self._report(progress_callback, 76.0, "Reading Power Query SDK output...")
            output_text = _decode_pqtest_text_output(output_path.read_text(encoding="utf-8"))
            records = json.loads(output_text or "[]")
            if not isinstance(records, list):
                raise ExtractionError("PQTest.exe returned an unexpected result shape for Pdf.Tables().")
            if not records:
                self._report(progress_callback, 77.0, "Power Query SDK completed but returned no table rows.")
                return []

            extracted_tables: list[ExtractedTable] = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                name = str(record.get("Name", "") or "")
                warnings_text = str(record.get("WarningText", "") or "")
                if warnings_text:
                    evaluation_warnings.extend(_dedupe_preserve_order(warnings_text.split(" || ")))

                headers_json = str(record.get("HeadersJson", "") or "[]")
                rows_json = str(record.get("RowsJson", "") or "[]")
                headers = [str(value).strip() for value in json.loads(headers_json)]
                data_rows = [
                    ["" if value is None else str(value).strip() for value in row]
                    for row in json.loads(rows_json)
                ]
                headers, data_rows = _normalize_power_query_table(headers, data_rows)
                raw_text = "\n".join(" | ".join(cell for cell in row) for row in [headers, *data_rows] if any(row))
                if not headers and not data_rows:
                    continue
                extracted_tables.append(
                    ExtractedTable(
                        page_number=_page_number_from_table_name(name),
                        headers=headers,
                        rows=data_rows,
                        import_headers=list(headers),
                        source_text=raw_text,
                        raw_text=raw_text,
                        confidence=0.93,
                        backend="power_query",
                    )
                )
            self._report(progress_callback, 77.0, f"Power Query returned {len(extracted_tables)} table candidate(s).")
            return extracted_tables
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(
                "PQTest.exe did not complete within 90 seconds while evaluating Pdf.Tables()."
            ) from exc
        except ExtractionError:
            raise
        except Exception as exc:  # pragma: no cover - SDK/runtime-specific failures
            detail = str(exc).strip() or type(exc).__name__
            raise ExtractionError(
                "Microsoft Power Query Pdf.Tables() SDK extraction failed. "
                "This backend requires the Power Query SDK toolchain with PQTest.exe available locally. "
                f"Details: {detail}"
            ) from exc
        finally:
            for temp_file in runtime_dir.glob("*"):
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            try:
                runtime_dir.rmdir()
            except OSError:
                pass

    @staticmethod
    def _build_power_query_formula(path: Path) -> str:
        escaped_path = str(path).replace('"', '""')
        return (
            "let\n"
            f'    Source = Pdf.Tables(File.Contents("{escaped_path}"), '
            '[Implementation="1.3", MultiPageTables=true, EnforceBorderLines=false]),\n'
            '    TablesOnly = Table.SelectRows(Source, each [Kind] = "Table"),\n'
            '    Indexed = Table.AddIndexColumn(TablesOnly, "TableIndex", 1, 1, Int64.Type),\n'
            '    HeadersJson = Table.AddColumn(Indexed, "HeadersJson", each Text.FromBinary(Json.FromValue(Table.ColumnNames([Data])), TextEncoding.Utf8), type text),\n'
            '    RowsJson = Table.AddColumn(HeadersJson, "RowsJson", each Text.FromBinary(Json.FromValue(Table.ToRows([Data])), TextEncoding.Utf8), type text),\n'
            '    WarningText = Table.AddColumn(RowsJson, "WarningText", each "", type text),\n'
            '    Output = Table.SelectColumns(WarningText, {"Name", "Kind", "TableIndex", "HeadersJson", "RowsJson", "WarningText"}),\n'
            '    JsonOutput = Text.FromBinary(Json.FromValue(Table.ToRecords(Output)), TextEncoding.Utf8)\n'
            "in\n"
            "    JsonOutput"
        )

    @staticmethod
    def _resolve_pqtest_path() -> Path:
        candidates: list[Path] = []
        env_path = os.environ.get("PQTEST_PATH", "").strip()
        if env_path:
            env_candidate = Path(env_path)
            candidates.append(env_candidate / "PQTest.exe" if env_candidate.is_dir() else env_candidate)

        vscode_extensions = _sdk_extension_root()
        if vscode_extensions.exists():
            sdk_roots = sorted(
                [path for path in vscode_extensions.glob("powerquery.vscode-powerquery-sdk-*") if path.is_dir()],
                reverse=True,
            )
            for root in sdk_roots:
                preferred = root / "PQTest.exe"
                packaged = [
                    candidate
                    for candidate in root.rglob("PQTest.exe")
                    if candidate != preferred
                ]
                if preferred.exists():
                    candidates.append(preferred)
                candidates.extend(sorted(packaged))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise ExtractionError(
            "PQTest.exe was not found in the default Power Query SDK extension location."
        )

    def _resolve_makepqx_path(self) -> Path:
        candidates: list[Path] = []
        env_path = os.environ.get("MAKEPQX_PATH", "").strip()
        if env_path:
            env_candidate = Path(env_path)
            candidates.append(env_candidate / "MakePQX.exe" if env_candidate.is_dir() else env_candidate)

        vscode_extensions = _sdk_extension_root()
        if vscode_extensions.exists():
            sdk_roots = sorted(
                [path for path in vscode_extensions.glob("powerquery.vscode-powerquery-sdk-*") if path.is_dir()],
                reverse=True,
            )
            for root in sdk_roots:
                preferred = root / "MakePQX.exe"
                packaged = [
                    candidate
                    for candidate in root.rglob("MakePQX.exe")
                    if candidate != preferred
                ]
                if preferred.exists():
                    candidates.append(preferred)
                candidates.extend(sorted(packaged))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise ExtractionError(
            "MakePQX.exe was not found in the default Power Query SDK extension location."
        )

    def _ensure_power_query_bootstrap_extension(self) -> Path:
        makepqx_path = self._resolve_makepqx_path()
        template_root = self._resolve_power_query_template_root()
        source_dir = POWER_QUERY_RUNTIME_DIR / "bootstrap_source"
        output_dir = POWER_QUERY_RUNTIME_DIR / "bootstrap_build"
        extension_path = output_dir / f"{POWER_QUERY_BOOTSTRAP_NAME}.mez"

        if extension_path.exists():
            return extension_path

        source_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_bootstrap_extension_source(source_dir, template_root)

        completed = subprocess.run(
            [str(makepqx_path), "compile", str(source_dir), "-d", str(output_dir), "-t", POWER_QUERY_BOOTSTRAP_NAME],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(makepqx_path.parent),
            env=_tool_launch_env(makepqx_path),
            timeout=POWER_QUERY_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0 or not extension_path.exists():
            detail = completed.stderr.strip() or completed.stdout.strip() or f"Exit code {completed.returncode}"
            raise ExtractionError(f"MakePQX.exe failed while building the bootstrap connector. Details: {detail}")

        return extension_path

    def _resolve_power_query_template_root(self) -> Path:
        sdk_roots = sorted(
            [
                path
                for path in _sdk_extension_root().glob("powerquery.vscode-powerquery-sdk-*")
                if path.is_dir()
            ],
            reverse=True,
        )
        for root in sdk_roots:
            template_root = root / "templates"
            if template_root.exists():
                return template_root
        raise ExtractionError("Power Query SDK templates were not found in the default extension location.")

    def _write_bootstrap_extension_source(self, source_dir: Path, template_root: Path) -> None:
        pq_template = (template_root / "PQConn.pq").read_text(encoding="utf-8")
        proj_template = (template_root / "PQConn.proj").read_text(encoding="utf-8")
        resx_template = (template_root / "resources.resx").read_text(encoding="utf-8")

        replacements = {
            "{{ProjectName}}": POWER_QUERY_BOOTSTRAP_NAME,
        }
        for filename, template_text in (
            (f"{POWER_QUERY_BOOTSTRAP_NAME}.pq", pq_template),
            (f"{POWER_QUERY_BOOTSTRAP_NAME}.proj", proj_template),
            ("resources.resx", resx_template),
        ):
            rendered = template_text
            for key, value in replacements.items():
                rendered = rendered.replace(key, value)
            (source_dir / filename).write_text(rendered, encoding="utf-8")

        for size in ("16", "20", "24", "32", "40", "48", "64", "80"):
            source_icon = template_root / f"PQConn{size}.png"
            target_icon = source_dir / f"{POWER_QUERY_BOOTSTRAP_NAME}{size}.png"
            if not target_icon.exists():
                target_icon.write_bytes(source_icon.read_bytes())

    def _extract_pdf_pages_with_local_ocr(
        self,
        path: Path,
        page_indices: list[int] | None,
        ocr_backend: str,
        ocr_language: str,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ExtractedSegment]:
        target_page_indices = page_indices or []
        if ocr_backend == "disabled":
            return [
                ExtractedSegment(
                    page_number=page_index + 1,
                    text="[OCR is disabled for this run and no native PDF text was extracted from this page.]",
                    confidence=0.0,
                    segment_type="ocr_disabled",
                )
                for page_index in target_page_indices
            ]

        if pypdfium2 is None or pytesseract is None:
            return [
                ExtractedSegment(
                    page_number=page_index + 1,
                    text="[No native PDF text extracted and Tesseract OCR is unavailable.]",
                    confidence=0.0,
                    segment_type="ocr_required",
                )
                for page_index in target_page_indices
            ]

        try:
            pdf = pypdfium2.PdfDocument(str(path))
        except Exception as exc:  # pragma: no cover - runtime-specific failure
            raise ExtractionError(f"Unable to open PDF for local OCR fallback: {path.name}") from exc

        segments: list[ExtractedSegment] = []
        try:
            if page_indices is None:
                target_page_indices = list(range(len(pdf)))

            total_pages = max(len(target_page_indices), 1)
            for position, page_index in enumerate(target_page_indices, start=1):
                page = pdf[page_index]
                try:
                    bitmap = page.render(scale=2.0)
                    image = bitmap.to_pil()
                    text, _ = _split_evaluation_warnings(pytesseract.image_to_string(image, lang=ocr_language) or "")
                finally:
                    page.close()

                segments.append(
                    ExtractedSegment(
                        page_number=page_index + 1,
                        text=text or "[No OCR text extracted from page.]",
                        confidence=0.65 if text else 0.0,
                        segment_type="ocr_page_text" if text else "ocr_required",
                    )
                )
                if progress_callback is not None:
                    progress = 75.0 + (20.0 * position / total_pages)
                    self._report(progress_callback, progress, "Running Tesseract OCR on PDF pages...")
        finally:
            pdf.close()

        return segments

    def _extract_docx(self, path: Path) -> SourceDocument:
        try:
            docx_document = DocxDocument(path)
        except Exception as exc:  # pragma: no cover - dependency-specific failures
            raise ExtractionError(f"Failed to read DOCX document: {path.name}") from exc

        paragraphs = [paragraph.text.strip() for paragraph in docx_document.paragraphs if paragraph.text.strip()]
        tables: list[ExtractedTable] = []
        for table in docx_document.tables:
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            rows = [row for row in rows if any(cell for cell in row)]
            if not rows:
                continue
            tables.append(
                ExtractedTable(
                    page_number=1,
                    headers=rows[0],
                    rows=rows[1:] if len(rows) > 1 else [],
                    import_headers=list(rows[0]),
                    source_text="\n".join(" | ".join(cell for cell in row) for row in rows),
                    raw_text="\n".join(" | ".join(cell for cell in row) for row in rows),
                    confidence=0.85,
                )
            )

        raw_docx_text_parts = [paragraph.text for paragraph in docx_document.paragraphs if paragraph.text]
        for table in docx_document.tables:
            for row in table.rows:
                row_values = [cell.text for cell in row.cells]
                raw_docx_text_parts.append("\t".join(row_values))

        document = SourceDocument(
            path=path,
            title=path.stem,
            raw_import_text="\n".join(raw_docx_text_parts),
            tables=tables,
        )
        if paragraphs:
            document.segments.append(
                ExtractedSegment(
                    page_number=1,
                    text="\n\n".join(paragraphs),
                    confidence=0.95,
                    segment_type="docx_text",
                )
            )
        if not document.segments and not document.tables:
            document.segments.append(
                ExtractedSegment(
                    page_number=1,
                    text="[No readable DOCX content was extracted.]",
                    confidence=0.0,
                    segment_type="extraction_gap",
                )
            )
        return document

    def _extract_text(self, path: Path) -> SourceDocument:
        text = path.read_text(encoding="utf-8")
        return SourceDocument(
            path=path,
            title=path.stem,
            raw_import_text=text,
            segments=[ExtractedSegment(page_number=1, text=text, confidence=1.0, segment_type="plain_text")],
        )

    @staticmethod
    def _report(
        progress_callback: ProgressCallback | None,
        percent: float,
        message: str,
    ) -> None:
        if progress_callback is not None:
            progress_callback(percent, message)

    @staticmethod
    def _safe_spire_dispose(resource: Any) -> None:
        for method_name in ("Dispose", "Close"):
            method = getattr(resource, method_name, None)
            if callable(method):
                method()
                return

    @staticmethod
    def _get_page_count(pdf_document: Any) -> int:
        pages = pdf_document.Pages
        count = getattr(pages, "Count", None)
        if count is None:
            raise ExtractionError("Spire.PDF did not expose the page collection count.")
        return int(count)

    @staticmethod
    def _get_spire_page(pdf_document: Any, page_index: int) -> Any:
        return pdf_document.Pages.get_Item(page_index)

    @staticmethod
    def _spire_attr(name: str) -> Any:
        for module in (spire_pdf, spire_pdf_common):
            if module is not None and hasattr(module, name):
                return getattr(module, name)
        raise ExtractionError(f"Spire.PDF does not expose the expected API member: {name}.")
