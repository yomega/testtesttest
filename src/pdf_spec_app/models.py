from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass(slots=True)
class TableSchema:
    name: str
    columns: list[str]
    aliases: dict[str, list[str]] = field(default_factory=dict)
    required_columns: list[str] = field(default_factory=list)
    start_header: str | None = None
    end_header: str | None = None
    weight: float = 1.5


@dataclass(slots=True)
class ExtractionOptions:
    ignore_tables: bool = False
    extract_tables: bool = True
    table_extraction_backend: str = "pdfplumber"
    pdfplumber_use_default_table_settings: bool = False
    pdfplumber_vertical_strategy: str = "lines"
    pdfplumber_horizontal_strategy: str = "lines"
    pdfplumber_text_x_tolerance: int = 3
    pdfplumber_text_y_tolerance: int = 3
    ocr_backend: str = "tesseract"
    ocr_language: str = "eng"
    manual_table_regions: list["ManualTableRegion"] = field(default_factory=list)


@dataclass(slots=True)
class ExtractedSegment:
    page_number: int
    text: str
    confidence: float = 1.0
    segment_type: str = "paragraph"


@dataclass(slots=True)
class ExtractedTable:
    page_number: int
    headers: list[str]
    rows: list[list[str]]
    import_headers: list[str] = field(default_factory=list)
    source_text: str = ""
    raw_text: str = ""
    raw_html: str | None = None
    confidence: float = 0.5
    backend: str = "unknown"
    header_source: str = "table_extract"
    matched_schema: str | None = None
    schema_score: float = 0.0
    schema_debug_notes: list[str] = field(default_factory=list)
    extraction_box: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class ManualTableRegion:
    page_number: int
    left: float
    top: float
    right: float
    bottom: float
    label: str = ""


@dataclass(slots=True)
class PagePreviewImage:
    page_number: int
    image_bytes: bytes
    image_width_px: int
    image_height_px: int
    page_width_pts: float
    page_height_pts: float


@dataclass(slots=True)
class SourceDocument:
    path: Path
    title: str
    raw_import_text: str = ""
    segments: list[ExtractedSegment] = field(default_factory=list)
    raw_tables: list[ExtractedTable] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    page_preview_images: list[PagePreviewImage] = field(default_factory=list)
    pdfplumber_debug_images: list[tuple[int, bytes]] = field(default_factory=list)
    extraction_debug: dict[str, str] = field(default_factory=dict)
    evaluation_warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceItem:
    page_number: int
    excerpt: str
    confidence: float
    source_type: str

    def to_formatted_string(self) -> str:
        """
        Returns a formatted string representation of the EvidenceItem.
        """
        return (
            f"  Page {self.page_number} | {self.source_type} | "
            f"{self.confidence:.2f} |\n{self.excerpt}"
        )


@dataclass(slots=True)
class SpecStatement:
    text: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "supported"


@dataclass(slots=True)
class SpecSection:
    title: str
    statements: list[SpecStatement] = field(default_factory=list)


@dataclass(slots=True)
class Specification:
    title: str
    source_path: Path
    sections: list[SpecSection] = field(default_factory=list)
    preview_warnings: list[str] = field(default_factory=list)

    def all_statements(self) -> Sequence[SpecStatement]:
        return [statement for section in self.sections for statement in section.statements]
