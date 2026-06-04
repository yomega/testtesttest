from __future__ import annotations

from pathlib import Path

from .models import ExtractedSegment, ExtractionOptions, SourceDocument
from .extractor_support import ExtractionError, _infer_tables_from_text, _split_evaluation_warnings


class OcrBackendMixin:
    def _extract_pdf_with_ocr_only(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback=None,
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

    def _extract_pdf_pages_with_local_ocr(
        self,
        path: Path,
        page_indices: list[int] | None,
        ocr_backend: str,
        ocr_language: str,
        progress_callback=None,
    ) -> list[ExtractedSegment]:
        pypdfium2 = self._pypdfium2_module()
        pytesseract = self._pytesseract_module()
        target_page_indices = page_indices

        page_count = 0
        if page_indices is None:
            try:
                preview_pdf = pypdfium2.PdfDocument(str(path)) if pypdfium2 is not None else None
            except Exception:
                preview_pdf = None
            if preview_pdf is not None:
                try:
                    page_count = len(preview_pdf)
                finally:
                    preview_pdf.close()
            target_page_indices = list(range(page_count)) if page_count > 0 else []

        if target_page_indices is None:
            target_page_indices = []

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
        except Exception as exc:  # pragma: no cover
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
