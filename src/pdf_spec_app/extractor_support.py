from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from .models import ExtractedTable, ExtractionOptions, ManualTableRegion


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
        raw_text = _form_markdown_table(rows)
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


def _describe_pdfplumber_revision_usage(pdf: Any) -> dict[str, str]:
    xrefs = list(getattr(getattr(pdf, "doc", None), "xrefs", []) or [])
    revision_count = len(xrefs)
    has_incremental_updates = revision_count > 1 or any(
        "Prev" in (getattr(xref, "trailer", None) or getattr(xref, "get_trailer", lambda: {})() or {})
        for xref in xrefs
    )
    return {
        "pdf_revision_count": str(revision_count or 1),
        "pdf_has_incremental_updates": str(bool(has_incremental_updates)),
        "pdf_revision_resolution": (
            "latest_revision_only_via_pdfminer_xref_chain"
            if has_incremental_updates
            else "single_revision"
        ),
    }


def _form_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""

    header = rows[0]
    body = rows[1:]

    markdown = "| " + " | ".join(header) + " |\n"
    markdown += "| " + " | ".join("---" for _ in header) + " |\n"
    for row in body:
        markdown += "| " + " | ".join(row) + " |\n"

    return markdown
