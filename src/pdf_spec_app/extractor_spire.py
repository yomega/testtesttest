from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ExtractedSegment, ExtractedTable, ExtractionOptions, SourceDocument
from .extractor_support import (
    ExtractionError,
    _append_raw_import_text,
    _dedupe_preserve_order,
    _form_markdown_table,
    _infer_tables_from_text,
    _split_evaluation_warnings,
)


class SpireBackendMixin:
    def _extract_pdf(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback=None,
    ) -> SourceDocument:
        if options.ocr_backend == "tesseract_only":
            return self._extract_pdf_with_ocr_only(path, options, progress_callback)

        if options.table_extraction_backend == "pdfplumber":
            return self._extract_pdf_with_pdfplumber(path, options, progress_callback)

        if self._spire_pdf_module() is None:
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

    def _create_spire_document(self, path: Path) -> Any:
        try:
            pdf_document = self._spire_attr("PdfDocument")()
            pdf_document.LoadFromFile(str(path))
            return pdf_document
        except Exception as exc:  # pragma: no cover
            raise ExtractionError(f"Spire.PDF could not open this PDF: {path.name}. Details: {exc}") from exc

    def _create_table_extractor(self, pdf_document: Any) -> Any | None:
        try:
            return self._spire_attr("PdfTableExtractor")(pdf_document)
        except Exception as exc:  # pragma: no cover
            raise ExtractionError(f"Spire.PDF could not initialize table extraction. Details: {exc}") from exc

    def _extract_spire_page_text(self, page: Any) -> str:
        text_extractor = self._spire_attr("PdfTextExtractor")(page)
        extract_options = self._spire_attr("PdfTextExtractOptions")()
        extract_options.IsShowHiddenText = False
        if hasattr(extract_options, "IsExtractAllText"):
            extract_options.IsExtractAllText = True
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
        except Exception as exc:  # pragma: no cover
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
            raw_text = _form_markdown_table(rows)
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
