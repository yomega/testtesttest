from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import ExtractedSegment, ExtractedTable, ExtractionOptions, ManualTableRegion, PagePreviewImage, SourceDocument
from .extractor_support import (
    PDFPLUMBER_DEBUG_IMAGE_RESOLUTION,
    ExtractionError,
    _append_raw_import_text,
    _describe_pdfplumber_revision_usage,
    _form_markdown_table,
    _group_manual_table_regions_by_page,
    _infer_tables_from_text,
    _normalize_extracted_rows,
    _pdfplumber_page_pixel_size,
    _pdfplumber_table_settings,
)
from .table_schemas import normalize_header
from .models import TableSchema


def _dedupe_pdfplumber_chars_prefer_latest(
    chars: list[dict[str, Any]],
    tolerance: float = 1.0,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for index, char in enumerate(chars):
        grouped[(char.get("upright"), char.get("text"))].append((index, char))

    selected: list[tuple[int, dict[str, Any]]] = []
    for group in grouped.values():
        kept: list[tuple[int, dict[str, Any]]] = []
        for index, char in group:
            replacement_index = None
            doctop = float(char.get("doctop", 0.0) or 0.0)
            x0 = float(char.get("x0", 0.0) or 0.0)
            for kept_index, (_original_index, kept_char) in enumerate(kept):
                kept_doctop = float(kept_char.get("doctop", 0.0) or 0.0)
                kept_x0 = float(kept_char.get("x0", 0.0) or 0.0)
                if abs(doctop - kept_doctop) <= tolerance and abs(x0 - kept_x0) <= tolerance:
                    replacement_index = kept_index
                    break
            if replacement_index is None:
                kept.append((index, char))
            else:
                kept[replacement_index] = (index, char)
        selected.extend(kept)

    return [
        char
        for _index, char in sorted(
            selected,
            key=lambda item: (
                float(item[1].get("doctop", 0.0) or 0.0),
                float(item[1].get("x0", 0.0) or 0.0),
                item[0],
            ),
        )
    ]


def _replace_table_settings_note(notes: list[str], settings_text: str) -> list[str]:
    filtered_notes = [note for note in notes if not note.startswith("Table settings:")]
    filtered_notes.append(f"Table settings: {settings_text}")
    return filtered_notes


def _group_words_for_object_text(
    words: list[dict[str, Any]],
    tolerance: float = 3.0,
) -> list[list[dict[str, Any]]]:
    sorted_words = sorted(
        words,
        key=lambda word: (
            float(word.get("doctop", 0.0) or 0.0),
            float(word.get("x0", 0.0) or 0.0),
        ),
    )
    lines: list[list[dict[str, Any]]] = []
    for word in sorted_words:
        doctop = float(word.get("doctop", 0.0) or 0.0)
        if not lines:
            lines.append([word])
            continue
        prior_doctop = float(lines[-1][0].get("doctop", 0.0) or 0.0)
        if abs(doctop - prior_doctop) <= tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda word: float(word.get("x0", 0.0) or 0.0))
    return lines


def _pdfplumber_word_object_token(word: dict[str, Any]) -> str:
    text = str(word.get("text", "") or "").replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'word(text="{text}", '
        f'x0={float(word.get("x0", 0.0) or 0.0):.2f}, '
        f'x1={float(word.get("x1", 0.0) or 0.0):.2f}, '
        f'top={float(word.get("top", 0.0) or 0.0):.2f}, '
        f'bottom={float(word.get("bottom", 0.0) or 0.0):.2f})'
    )


def _format_pdfplumber_object_text_page(
    page: Any,
    words: list[dict[str, Any]],
) -> str:
    if not words:
        return "[No pdfplumber word objects are available for this page.]"

    bbox = getattr(
        page,
        "bbox",
        (0.0, 0.0, float(getattr(page, "width", 0.0) or 0.0), float(getattr(page, "height", 0.0) or 0.0)),
    )
    page_left = float(bbox[0] or 0.0)
    char_widths = [
        float(word.get("x1", 0.0) or 0.0) - float(word.get("x0", 0.0) or 0.0)
        for word in words
        if str(word.get("text", "") or "")
    ]
    char_counts = [len(str(word.get("text", "") or "")) for word in words if str(word.get("text", "") or "")]
    width_samples = [
        width / max(count, 1)
        for width, count in zip(char_widths, char_counts)
        if width > 0 and count > 0
    ]
    avg_char_width = sum(width_samples) / len(width_samples) if width_samples else 6.0
    avg_char_width = max(avg_char_width, 1.0)

    rendered_lines: list[str] = []
    for line_words in _group_words_for_object_text(words):
        if not line_words:
            continue
        line_parts: list[str] = []
        line_cursor = page_left
        for index, word in enumerate(line_words):
            word_left = float(word.get("x0", 0.0) or 0.0)
            if index == 0:
                gap = max(0.0, word_left - page_left)
            else:
                gap = max(0.0, word_left - line_cursor)
            spaces = int(round(gap / avg_char_width))
            if index > 0:
                spaces = max(1, spaces)
            if spaces > 0:
                line_parts.append(" " * spaces)
            token = _pdfplumber_word_object_token(word)
            line_parts.append(token)
            line_cursor = float(word.get("x1", 0.0) or 0.0)
        rendered_lines.append("".join(line_parts).rstrip())
    return "\n".join(rendered_lines)


class PdfPlumberBackendMixin:
    def refine_pdfplumber_tables_with_schema(
        self,
        file_path: str | Path,
        tables: list[ExtractedTable],
        schemas: list[TableSchema],
        options: ExtractionOptions,
    ) -> list[ExtractedTable]:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return tables
        if options.table_extraction_backend != "pdfplumber":
            return tables

        pdfplumber = self._pdfplumber_module()
        if pdfplumber is None:
            return tables

        schema_by_name = {schema.name: schema for schema in schemas}
        refined_tables = list(tables)
        try:
            with pdfplumber.open(str(path)) as pdf:
                for index, table in enumerate(refined_tables):
                    schema = schema_by_name.get(table.matched_schema or "")
                    if schema is None or not str(table.backend).startswith("pdfplumber"):
                        continue
                    page_index = max(0, table.page_number - 1)
                    if page_index >= len(pdf.pages):
                        continue
                    page = self._dedupe_pdfplumber_page(pdf.pages[page_index])
                    refined = self._refine_pdfplumber_table_from_schema(page, table, schema, options)
                    if refined is not None:
                        refined_tables[index] = refined
        except Exception:
            return tables
        return refined_tables

    def generate_pdfplumber_debug_images(
        self,
        file_path: str | Path,
        options: ExtractionOptions | None = None,
        tables: list[ExtractedTable] | None = None,
    ) -> list[tuple[int, bytes, str, str]]:
        options = options or ExtractionOptions()
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return []
        pdfplumber = self._pdfplumber_module()
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        debug_images: list[tuple[int, bytes, str, str]] = []
        manual_regions_by_page = _group_manual_table_regions_by_page(options.manual_table_regions)
        tables_by_page: dict[int, list[ExtractedTable]] = defaultdict(list)
        for table in tables or []:
            if str(table.backend).startswith("pdfplumber") and (
                table.extraction_vertical_lines or table.extraction_column_bounds
            ):
                tables_by_page[table.page_number].append(table)
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    page_number = page_index + 1
                    effective_page = self._dedupe_pdfplumber_page(page)
                    page_tables = tables_by_page.get(page_number, [])
                    if page_tables:
                        debug_images.extend(
                            self._capture_pdfplumber_schema_rescan_debug_images(
                                effective_page,
                                page_number,
                                options,
                                page_tables,
                            )
                        )
                    else:
                        page_regions = manual_regions_by_page.get(page_number, [])
                        debug_images.extend(
                            self._capture_pdfplumber_debug_tablefinder_images(
                                effective_page,
                                page_number,
                                options,
                                page_regions,
                            )
                        )
        except Exception as exc:  # pragma: no cover
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
        pdfplumber = self._pdfplumber_module()
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        previews: list[PagePreviewImage] = []
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    preview = self._render_pdfplumber_page_preview(page, page_index + 1, resolution)
                    if preview is not None:
                        previews.append(preview)
        except Exception as exc:  # pragma: no cover
            raise ExtractionError(f"pdfplumber could not render page previews for this PDF: {path.name}. Details: {exc}") from exc

        return previews

    def _extract_pdf_with_pdfplumber(
        self,
        path: Path,
        options: ExtractionOptions,
        progress_callback=None,
    ) -> SourceDocument:
        pdfplumber = self._pdfplumber_module()
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
        object_debug_pages: list[tuple[int, str]] = []

        try:
            with pdfplumber.open(str(path)) as pdf:
                source_document.extraction_debug.update(_describe_pdfplumber_revision_usage(pdf))
                source_document.extraction_debug["pdfplumber_char_resolution"] = "prefer_latest_overlapping_chars"
                if source_document.extraction_debug["pdf_has_incremental_updates"] == "True":
                    source_document.evaluation_warnings.append(
                        "Incremental PDF updates were detected. The pdfplumber backend is using only the latest resolved object values from the final xref revision chain."
                    )
                page_total = len(pdf.pages)
                for page_index, page in enumerate(pdf.pages):
                    page_number = page_index + 1
                    effective_page = self._dedupe_pdfplumber_page(page)
                    page_width_px, page_height_px = _pdfplumber_page_pixel_size(effective_page)
                    max_page_width_px = max(max_page_width_px, page_width_px)
                    max_page_height_px = max(max_page_height_px, page_height_px)
                    preview = self._render_pdfplumber_page_preview(page, page_number)
                    if preview is not None:
                        source_document.page_preview_images.append(preview)
                    try:
                        raw_page_text = effective_page.extract_text(layout=options.preserve_layout) or ""
                    except TypeError:
                        raw_page_text = effective_page.extract_text() or ""
                    try:
                        page_words = effective_page.extract_words(return_chars=True) or []
                    except TypeError:
                        try:
                            page_words = effective_page.extract_words() or []
                        except Exception:
                            page_words = []
                    except Exception:
                        page_words = []
                    object_debug_pages.append(
                        (page_number, _format_pdfplumber_object_text_page(effective_page, page_words))
                    )
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

                    page_regions = manual_regions_by_page.get(page_number, [])
                    schema_guided_settings, schema_guided_label, schema_guided_notes = self._schema_guided_page_settings(
                        effective_page,
                        page_number,
                        options,
                    )
                    source_document.pdfplumber_debug_images.extend(
                        self._capture_pdfplumber_debug_tablefinder_images(
                            effective_page,
                            page_number,
                            options,
                            page_regions,
                            page_settings_override=schema_guided_settings,
                            page_label_override=schema_guided_label,
                        )
                    )

                    if options.extract_tables:
                        page_tables: list[ExtractedTable] = []
                        if page_regions:
                            page_tables.extend(
                                self._extract_pdfplumber_tables_from_regions(
                                    effective_page,
                                    page_number,
                                    raw_page_text,
                                    options,
                                    page_regions,
                                )
                            )
                        elif not page_tables:
                            page_settings = _pdfplumber_table_settings(options)
                            page_tables.extend(
                                self._build_pdfplumber_tables_from_rows(
                                    self._extract_pdfplumber_tables_from_page(
                                        effective_page,
                                        options,
                                        table_settings_override=schema_guided_settings,
                                    ),
                                    page_number,
                                    raw_page_text,
                                    backend="pdfplumber",
                                    extraction_box=self._page_box_tuple(page),
                                    extraction_debug_notes=schema_guided_notes,
                                    extraction_settings_text=self._format_pdfplumber_settings_text(page_settings),
                                    extraction_words=page_words,
                                )
                            )
                        source_document.tables.extend(page_tables)

                    progress = 20.0 + (50.0 * page_number / max(page_total, 1))
                    self._report(progress_callback, progress, "Extracting PDF pages with pdfplumber...")
        except Exception as exc:  # pragma: no cover
            raise ExtractionError(f"pdfplumber could not open or extract this PDF: {path.name}. Details: {exc}") from exc

        source_document.extraction_debug["pdfplumber_max_page_width_px"] = str(max_page_width_px or 1)
        source_document.extraction_debug["pdfplumber_max_page_height_px"] = str(max_page_height_px or 1)
        source_document.extraction_debug["manual_table_regions"] = str(len(options.manual_table_regions))
        source_document.pdfplumber_object_debug_pages = list(object_debug_pages)
        source_document.pdfplumber_object_debug_text = "\n\n".join(page_text for _page_number, page_text in object_debug_pages)

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

    def _capture_pdfplumber_debug_tablefinder_images(
        self,
        page: Any,
        page_number: int,
        options: ExtractionOptions,
        regions: list[ManualTableRegion],
        page_settings_override: dict[str, Any] | None = None,
        page_label_override: str | None = None,
    ) -> list[tuple[int, bytes, str, str]]:
        default_settings = _pdfplumber_table_settings(options)
        default_settings_text = self._format_pdfplumber_settings_text(default_settings)
        if not regions:
            debug_png = self._capture_pdfplumber_debug_tablefinder(
                page,
                options,
                table_settings_override=page_settings_override,
            )
            return [(page_number, debug_png, page_label_override or f"Page {page_number}")] if debug_png is not None else []

        debug_images: list[tuple[int, bytes, str, str]] = []
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
            region_settings = self._pdfplumber_region_table_settings(cropped_page, options)
            debug_png = self._capture_pdfplumber_debug_tablefinder(
                cropped_page,
                options,
                table_settings_override=region_settings,
            )
            if debug_png is not None:
                debug_images.append(
                    (
                        page_number,
                        debug_png,
                        self._manual_region_debug_label(page_number, region, index),
                        self._format_pdfplumber_settings_text(region_settings),
                    )
                )
        return debug_images

    def _capture_pdfplumber_schema_rescan_debug_images(
        self,
        page: Any,
        page_number: int,
        options: ExtractionOptions,
        tables: list[ExtractedTable],
    ) -> list[tuple[int, bytes, str, str]]:
        debug_images: list[tuple[int, bytes, str, str]] = []
        for index, table in enumerate(tables, start=1):
            try:
                scoped_page = page.crop(table.extraction_box) if table.extraction_box is not None else page
            except Exception:
                scoped_page = page
            rescan_settings = self._pdfplumber_schema_rescan_table_settings(scoped_page, table, options)
            debug_png = self._capture_pdfplumber_debug_tablefinder(
                scoped_page,
                options,
                table_settings_override=rescan_settings,
            )
            if debug_png is not None:
                vertical_lines = rescan_settings.get("explicit_vertical_lines") or []
                debug_images.append(
                    (
                        page_number,
                        debug_png,
                        (
                            f"Page {page_number} | {(table.matched_schema or 'table')} rescan {index}"
                            f" | {len(vertical_lines)} explicit v-lines"
                        ),
                        self._format_pdfplumber_settings_text(rescan_settings),
                    )
                )
        return debug_images

    def _capture_pdfplumber_debug_tablefinder(
        self,
        page: Any,
        options: ExtractionOptions,
        table_settings_override: dict[str, Any] | None = None,
    ) -> bytes | None:
        table_settings = table_settings_override if table_settings_override is not None else _pdfplumber_table_settings(options)
        try:
            page_image = page.to_image(resolution=PDFPLUMBER_DEBUG_IMAGE_RESOLUTION)
            debug_image = page_image.debug_tablefinder() if table_settings is None else page_image.debug_tablefinder(table_settings)
            if table_settings is not None:
                explicit_vertical_lines = table_settings.get("explicit_vertical_lines") or []
                explicit_horizontal_lines = table_settings.get("explicit_horizontal_lines") or []
                if explicit_vertical_lines:
                    debug_image.draw_vlines(list(explicit_vertical_lines), stroke=(0, 200, 255, 255), stroke_width=2)
                if explicit_horizontal_lines:
                    debug_image.draw_hlines(list(explicit_horizontal_lines), stroke=(255, 140, 0, 255), stroke_width=2)
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
        extraction_box: tuple[float, float, float, float] | None = None,
        extraction_debug_notes: list[str] | None = None,
        extraction_settings_text: str | None = None,
        extraction_words: list[dict[str, Any]] | None = None,
    ) -> list[ExtractedTable]:
        built_tables: list[ExtractedTable] = []
        for extracted_rows in extracted_tables:
            rows = _normalize_extracted_rows(extracted_rows)
            if len(rows) < 2:
                continue
            headers = rows[0]
            body = rows[1:]
            raw_text = _form_markdown_table(rows)
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
                    extraction_debug_notes=list(extraction_debug_notes or []),
                    extraction_box=extraction_box,
                    extraction_words=list(extraction_words or []),
                    extraction_debug_notes=(
                        [f"Table settings: {extraction_settings_text}"] if extraction_settings_text else []
                    ),
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
            try:
                cropped_text = cropped_page.extract_text(layout=options.preserve_layout) or page_source_text
            except TypeError:
                cropped_text = cropped_page.extract_text() or page_source_text
            try:
                cropped_words = cropped_page.extract_words(return_chars=True) or []
            except TypeError:
                try:
                    cropped_words = cropped_page.extract_words() or []
                except Exception:
                    cropped_words = []
            except Exception:
                cropped_words = []
            region_settings = self._pdfplumber_region_table_settings(cropped_page, options)
            extracted_tables = self._extract_pdfplumber_tables_from_page(
                cropped_page,
                options,
                table_settings_override=region_settings,
            )
            built_tables = self._build_pdfplumber_tables_from_rows(
                extracted_tables,
                page_number,
                cropped_text,
                backend="pdfplumber_region",
                extraction_box=bbox,
                extraction_settings_text=self._format_pdfplumber_settings_text(region_settings),
                extraction_words=cropped_words,
            )
            if not built_tables and cropped_text:
                built_tables = _infer_tables_from_text(page_number, cropped_text)
                for table in built_tables:
                    table.backend = "pdfplumber_region_text_fallback"
                    table.extraction_box = bbox
                    table.extraction_words = list(cropped_words)
            label = region.label or f"region {index}"
            region_settings_text = json.dumps(region_settings, sort_keys=True)
            for table in built_tables:
                table.raw_text = table.raw_text or cropped_text
                table.extraction_debug_notes.append(f"Manual region: {label}")
                table.extraction_debug_notes.append(f"Region settings: {region_settings_text}")
                table.schema_debug_notes.append(f"Extracted from manual region: {label}")
            region_tables.extend(built_tables)
        return region_tables

    @staticmethod
    def _page_box_tuple(page: Any) -> tuple[float, float, float, float] | None:
        bbox = getattr(page, "bbox", None)
        if not bbox or len(bbox) != 4:
            return None
        return tuple(float(value) for value in bbox)

    def _extract_pdfplumber_tables_from_page_with_settings(
        self,
        page: Any,
        table_settings: dict[str, Any] | None,
    ) -> list[list[list[Any]]]:
        collected_tables: list[list[list[Any]]] = []
        seen_signatures: set[str] = set()

        found_tables: list[Any] = []
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

        if found_tables:
            extracted_tables = [table.extract(**((table_settings or {}).get("text_settings") or {})) for table in found_tables]
        else:
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

        for extracted_rows in extracted_tables:
            normalized_rows = _normalize_extracted_rows(extracted_rows)
            if len(normalized_rows) < 2:
                continue
            signature = _form_markdown_table(normalized_rows)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            collected_tables.append(extracted_rows)

        return collected_tables

    def _extract_pdfplumber_tables_from_page(
        self,
        page: Any,
        options: ExtractionOptions,
        table_settings_override: dict[str, Any] | None = None,
    ) -> list[list[list[Any]]]:
        table_settings = table_settings_override if table_settings_override is not None else _pdfplumber_table_settings(options)
        return self._extract_pdfplumber_tables_from_page_with_settings(page, table_settings)

    @staticmethod
    def _pdfplumber_region_table_settings(page: Any, options: ExtractionOptions) -> dict[str, Any]:
        settings = dict(_pdfplumber_table_settings(options) or {})
        bbox = getattr(
            page,
            "bbox",
            (0.0, 0.0, float(getattr(page, "width", 0.0) or 0.0), float(getattr(page, "height", 0.0) or 0.0)),
        )
        settings["vertical_strategy"] = "explicit"
        settings["explicit_vertical_lines"] = settings.get("explicit_vertical_lines", []) + [float(bbox[0]), float(bbox[2])]
        settings["explicit_horizontal_lines"] = settings.get("explicit_horizontal_lines", []) + [float(bbox[1]), float(bbox[3])]
        return settings

    def _schema_guided_page_settings(
        self,
        page: Any,
        page_number: int,
        options: ExtractionOptions,
    ) -> tuple[dict[str, Any] | None, str | None, list[str]]:
        if not options.schema_hints:
            return None, None, []

        line_match = self._best_schema_guided_line_match(page, options)
        if line_match is None:
            return None, None, []

        schema_name, line_text, line_box = line_match
        settings = self._schema_guided_table_settings(page, options, line_box)
        settings_text = json.dumps(settings, sort_keys=True)
        notes = [
            f"Schema-guided re-extract: {schema_name}",
            f"Matched line: {line_text}",
            f"Schema-guided settings: {settings_text}",
        ]
        return settings, f"Page {page_number} | schema-guided {schema_name}", notes

    def _best_schema_guided_line_match(
        self,
        page: Any,
        options: ExtractionOptions,
    ) -> tuple[str, str, tuple[float, float, float, float]] | None:
        words = self._extract_pdfplumber_words(page)
        if not words:
            return None

        best_match: tuple[float, str, str, tuple[float, float, float, float]] | None = None
        for line_words in self._group_words_into_lines(words):
            line_text = " ".join(str(word.get("text", "") or "").strip() for word in line_words).strip()
            if not line_text:
                continue
            for schema in options.schema_hints:
                score = self._schema_guided_line_score(line_text, schema)
                if score < 0.9:
                    continue
                line_box = (
                    min(float(word.get("x0", 0.0) or 0.0) for word in line_words),
                    min(float(word.get("top", 0.0) or 0.0) for word in line_words),
                    max(float(word.get("x1", 0.0) or 0.0) for word in line_words),
                    max(float(word.get("bottom", 0.0) or 0.0) for word in line_words),
                )
                candidate = (score, schema.name, line_text, line_box)
                if best_match is None or candidate[0] > best_match[0]:
                    best_match = candidate

        if best_match is None:
            return None
        return best_match[1], best_match[2], best_match[3]

    @staticmethod
    def _extract_pdfplumber_words(page: Any) -> list[dict[str, Any]]:
        try:
            return page.extract_words(use_text_flow=True) or []
        except TypeError:
            try:
                return page.extract_words() or []
            except Exception:
                return []
        except Exception:
            return []

    @staticmethod
    def _group_words_into_lines(words: list[dict[str, Any]], tolerance: float = 3.0) -> list[list[dict[str, Any]]]:
        ordered = sorted(
            words,
            key=lambda word: (
                float(word.get("top", 0.0) or 0.0),
                float(word.get("x0", 0.0) or 0.0),
            ),
        )
        lines: list[list[dict[str, Any]]] = []
        for word in ordered:
            top = float(word.get("top", 0.0) or 0.0)
            if not lines:
                lines.append([word])
                continue
            current_line = lines[-1]
            current_top = float(current_line[0].get("top", 0.0) or 0.0)
            if abs(top - current_top) <= tolerance:
                current_line.append(word)
            else:
                lines.append([word])
        return lines

    @staticmethod
    def _schema_guided_line_score(line_text: str, schema: Any) -> float:
        normalized_line = PdfPlumberBackendMixin._normalize_schema_text(line_text)
        if not normalized_line:
            return 0.0

        terms = PdfPlumberBackendMixin._schema_hint_terms(schema)
        matched = [term for term in terms if term and term in normalized_line]
        if not matched:
            return 0.0

        if schema.required_columns:
            required_terms = [PdfPlumberBackendMixin._normalize_schema_text(value) for value in schema.required_columns]
            if any(required_term and required_term not in normalized_line for required_term in required_terms):
                return 0.0

        score = len(matched) / max(len(terms), 1)
        if schema.start_header and PdfPlumberBackendMixin._normalize_schema_text(schema.start_header) in normalized_line:
            score += 0.35
        if schema.end_header and PdfPlumberBackendMixin._normalize_schema_text(schema.end_header) in normalized_line:
            score += 0.35
        return score * float(getattr(schema, "weight", 1.0) or 1.0)

    @staticmethod
    def _schema_hint_terms(schema: Any) -> list[str]:
        terms: list[str] = []
        for value in [*list(getattr(schema, "columns", []) or []), getattr(schema, "start_header", None), getattr(schema, "end_header", None)]:
            normalized = PdfPlumberBackendMixin._normalize_schema_text(value or "")
            if normalized and normalized not in terms:
                terms.append(normalized)
        return terms

    @staticmethod
    def _normalize_schema_text(value: str) -> str:
        stripped = re.sub(r"\(cid\s*:\s*\d+\)", " ", value, flags=re.IGNORECASE)
        stripped = re.sub(r"\bcid\s*[:#]?\s*\d+\b", " ", stripped, flags=re.IGNORECASE)
        normalized = re.sub(r"[^a-z0-9]+", " ", stripped.casefold()).strip()
        return re.sub(r"\s+", " ", normalized)

    @staticmethod
    def _schema_guided_table_settings(
        page: Any,
        options: ExtractionOptions,
        line_box: tuple[float, float, float, float],
    ) -> dict[str, Any]:
        settings = dict(_pdfplumber_table_settings(options) or {})
        explicit_vertical_lines = list(settings.get("explicit_vertical_lines", []))
        explicit_horizontal_lines = list(settings.get("explicit_horizontal_lines", []))
        left, top, right, bottom = line_box
        explicit_vertical_lines.extend([max(left - 1.0, 0.0), min(right + 1.0, float(getattr(page, "width", right) or right))])
        explicit_horizontal_lines.extend([max(top - 1.0, 0.0), min(bottom + 1.0, float(getattr(page, "height", bottom) or bottom))])
        settings["explicit_vertical_lines"] = sorted({round(value, 3) for value in explicit_vertical_lines})
        settings["explicit_horizontal_lines"] = sorted({round(value, 3) for value in explicit_horizontal_lines})
        return settings

    @staticmethod
    def _manual_region_debug_label(page_number: int, region: ManualTableRegion, index: int) -> str:
        label = region.label.strip() if region.label else ""
        return f"Page {page_number} | {label or f'Region {index}'}"

    @staticmethod
    def _dedupe_pdfplumber_page(page: Any) -> Any:
        try:
            filtered_page = page.filter(lambda _obj: True)
            filtered_page._objects = {kind: objs for kind, objs in page.objects.items()}
            filtered_page._objects["char"] = _dedupe_pdfplumber_chars_prefer_latest(list(page.chars))
            return filtered_page
        except Exception:
            return page

    def _refine_pdfplumber_table_from_schema(
        self,
        page: Any,
        table: ExtractedTable,
        schema: TableSchema,
        options: ExtractionOptions,
    ) -> ExtractedTable | None:
        try:
            scoped_page = page.crop(table.extraction_box) if table.extraction_box is not None else page
        except Exception:
            scoped_page = page

        words = list(table.extraction_words or [])
        if not words:
            try:
                words = scoped_page.extract_words(return_chars=True) or []
            except TypeError:
                try:
                    words = scoped_page.extract_words() or []
                except Exception:
                    return None
            except Exception:
                return None
        
        if not words:
            return None

        header_match = self._find_schema_header_line(words, schema, options)
        if header_match is None:
            return None

        header_words, matches, delineation_words, delineation_source = header_match
        column_bounds, vertical_lines = self._header_words_to_column_geometry(delineation_words, matches, scoped_page)

        if len(column_bounds) < 2:
            return None

        rescan_settings = self._pdfplumber_schema_rescan_table_settings(
            scoped_page,
            table,
            options,
            column_bounds=column_bounds,
            vertical_lines=vertical_lines,
        )
        
        headers = [match["label"] for match in matches]
        rows = self._extract_rows_by_pdfplumber_settings(scoped_page, headers, rescan_settings)
        if not rows:
            rows = self._extract_rows_by_column_bounds(words, header_words, column_bounds, options)
        if not rows:
            return None
        rescan_settings_text = self._format_pdfplumber_settings_text(rescan_settings)

        refined = ExtractedTable(
            page_number=table.page_number,
            headers=headers,
            rows=rows,
            import_headers=list(table.import_headers or table.headers),
            source_text=table.source_text,
            raw_text=_form_markdown_table([headers, *rows]),
            raw_html=table.raw_html,
            confidence=min(1.0, table.confidence + 0.04),
            backend=table.backend,
            header_source="pdfplumber_schema_rescan",
            matched_schema=table.matched_schema,
            schema_score=table.schema_score,
            extraction_debug_notes=[
                *_replace_table_settings_note(list(table.extraction_debug_notes), rescan_settings_text),
                "Refined with pdfplumber schema header rescan.",
                f"Rescan word source: {'initial extraction' if table.extraction_words else 'rescanned page query'}",
                f"Rescan available word count: {len(words)}",
                f"Rescan headers: {headers}",
                f"Rescan matched header object count: {len(header_words)}",
                f"Rescan expected schema header count: {self._schema_header_count(schema)}",
                f"Rescan delineation source: {delineation_source}",
                f"Rescan bounds: {column_bounds}",
                f"Rescan vertical lines: {vertical_lines}",
            ],
            schema_debug_notes=list(table.schema_debug_notes),
            extraction_box=table.extraction_box,
            extraction_column_bounds=list(column_bounds),
            extraction_vertical_lines=list(vertical_lines),
            extraction_words=list(words),
        )
        return refined

    def _find_schema_header_line(
        self,
        words: list[dict[str, Any]],
        schema: TableSchema,
        options: ExtractionOptions,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str] | None:
        expected_count = self._schema_header_count(schema)
        best_match: tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str] | None = None
        for line_words in self._group_pdfplumber_words_into_lines(words, options):
            matches = self._match_schema_headers_in_line(line_words, schema)
            
            if matches is None:
                continue
            
            matched_header_words = self._matches_to_header_words(matches)
            delineation_words, delineation_source = self._header_delineation_words_for_line(
                line_words,
                matched_header_words,
                schema,
            )
            if len(matched_header_words) == expected_count:
                return matched_header_words, matches, delineation_words, delineation_source
            if best_match is None or len(matched_header_words) > len(best_match[0]):
                best_match = (matched_header_words, matches, delineation_words, delineation_source)
        return best_match

    def _header_delineation_words_for_line(
        self,
        line_words: list[dict[str, Any]],
        matched_header_words: list[dict[str, Any]],
        schema: TableSchema,
    ) -> tuple[list[dict[str, Any]], str]:
        expected_count = self._schema_header_count(schema)
        if len(line_words) == expected_count:
            exact_word_matches = self._match_schema_header_words_exact(line_words, schema)
            if exact_word_matches is not None:
                return exact_word_matches, "word_objects"
        return matched_header_words, "merged_schema_matches"

    def _match_schema_header_words_exact(
        self,
        line_words: list[dict[str, Any]],
        schema: TableSchema,
    ) -> list[dict[str, Any]] | None:
        aliases_by_label = self._schema_alias_sequences(schema)
        if len(line_words) != len(aliases_by_label):
            return None
        available_indexes = list(range(len(line_words)))
        matched_words: list[dict[str, Any]] = []
        for _label, alias_sequences in aliases_by_label:
            matched_index = None
            for index in available_indexes:
                normalized_word = normalize_header(str(line_words[index].get("text", "") or ""))
                if any(len(alias_tokens) == 1 and normalized_word == alias_tokens[0] for alias_tokens in alias_sequences):
                    matched_index = index
                    break
            if matched_index is None:
                return None
            matched_words.append(line_words[matched_index])
            available_indexes.remove(matched_index)
        return sorted(matched_words, key=lambda word: float(word.get("x0", 0.0) or 0.0))

    def _group_pdfplumber_words_into_lines(
        self,
        words: list[dict[str, Any]],
        options: ExtractionOptions,
    ) -> list[list[dict[str, Any]]]:
        tolerance = max(1.0, float(options.pdfplumber_text_y_tolerance))
        sorted_words = sorted(
            words,
            key=lambda word: (
                float(word.get("doctop", 0.0) or 0.0),
                float(word.get("x0", 0.0) or 0.0),
            ),
        )
        lines: list[list[dict[str, Any]]] = []
        for word in sorted_words:
            doctop = float(word.get("doctop", 0.0) or 0.0)
            if not lines:
                lines.append([word])
                continue
            prior_doctop = float(lines[-1][0].get("doctop", 0.0) or 0.0)
            word_top = float(word.get("top", 0.0) or 0.0)
            word_bottom = float(word.get("bottom", 0.0) or 0.0)
            prior_top = min(float(existing.get("top", 0.0) or 0.0) for existing in lines[-1])
            prior_bottom = max(float(existing.get("bottom", 0.0) or 0.0) for existing in lines[-1])
            vertical_overlap = min(word_bottom, prior_bottom) - max(word_top, prior_top)
            same_visual_line = vertical_overlap >= -tolerance
            if abs(doctop - prior_doctop) <= tolerance or same_visual_line:
                lines[-1].append(word)
            else:
                lines.append([word])
        for line in lines:
            line.sort(key=lambda word: float(word.get("x0", 0.0) or 0.0))
        return lines

    def _match_schema_headers_in_line(
        self,
        line_words: list[dict[str, Any]],
        schema: TableSchema,
    ) -> list[dict[str, Any]] | None:
        aliases_by_label = self._schema_alias_sequences(schema)
        normalized_entries = [
            {
                "word": word,
                "normalized": normalize_header(str(word.get("text", "") or "")),
                "original_index": index,
            }
            for index, word in enumerate(line_words)
        ]
        print("--")
        
        print(line_words)
        normalized_entries = [entry for entry in normalized_entries if entry["normalized"]]
        
        if len(normalized_entries) < 2:
            return None
        normalized_words = [str(entry["normalized"]) for entry in normalized_entries]
        matches: list[dict[str, Any]] = []
        used_word_indexes: set[int] = set()

        for label, alias_sequences in aliases_by_label:
            best_match: dict[str, Any] | None = None
            for start_index in range(len(normalized_words)):
                for alias_tokens in alias_sequences:
                    width = len(alias_tokens)
                    if width == 0 or start_index + width > len(normalized_words):
                        continue
                    if any(index in used_word_indexes for index in range(start_index, start_index + width)):
                        continue
                    if normalized_words[start_index : start_index + width] != alias_tokens:
                        continue
                    matched_entries = normalized_entries[start_index : start_index + width]
                    matched_words = [entry["word"] for entry in matched_entries]
                    best_match = {
                        "label": " ".join(str(word.get("text", "") or "").strip() for word in matched_words).strip(),
                        "x0": float(matched_words[0].get("x0", 0.0) or 0.0),
                        "x1": float(matched_words[-1].get("x1", 0.0) or 0.0),
                        "top": float(matched_words[0].get("top", 0.0) or 0.0),
                        "bottom": float(matched_words[0].get("bottom", 0.0) or 0.0),
                        "indices": tuple(range(start_index, start_index + width)),
                        "original_indices": tuple(int(entry["original_index"]) for entry in matched_entries),
                    }
                    break
                if best_match is not None:
                    used_word_indexes.update(best_match["indices"])
                    matches.append(best_match)
                    break

        required = [label for label in schema.required_columns if label]
        if required:
            matched_required = {
                normalize_header(match["label"])
                for match in matches
            }
            if not all(any(normalize_header(column) == matched for matched in matched_required) for column in required):
                return None

        if schema.start_header and schema.end_header:
            normalized_matches = [normalize_header(match["label"]) for match in matches]
            if normalize_header(schema.start_header) not in normalized_matches or normalize_header(schema.end_header) not in normalized_matches:
                return None

        if len(matches) < 2:
            return None
        return sorted(matches, key=lambda match: (match["x0"], match["x1"]))

    @staticmethod
    def _schema_alias_sequences(schema: TableSchema) -> list[tuple[str, list[list[str]]]]:
        labels: list[str] = []
        for label in [*schema.columns, schema.start_header, schema.end_header]:
            if label and label not in labels:
                labels.append(label)
        sequences: list[tuple[str, list[list[str]]]] = []
        for label in labels:
            alias_values = [label, *schema.aliases.get(label, [])]
            token_sequences: list[list[str]] = []
            for alias in alias_values:
                normalized = normalize_header(alias)
                if not normalized:
                    continue
                tokens = normalized.split()
                if tokens and tokens not in token_sequences:
                    token_sequences.append(tokens)
            if token_sequences:
                sequences.append((label, token_sequences))
        return sequences

    @staticmethod
    def _schema_header_count(schema: TableSchema) -> int:
        labels: list[str] = []
        for label in schema.columns:
            if label and label not in labels:
                labels.append(label)
        if labels:
            return len(labels)

        fallback_labels: list[str] = []
        for label in [*schema.required_columns, schema.start_header, schema.end_header]:
            if label and label not in fallback_labels:
                fallback_labels.append(label)
        return len(fallback_labels)

    @staticmethod
    def _matches_to_header_words(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        header_words: list[dict[str, Any]] = []
        for match in matches:
            header_words.append(
                {
                    "text": str(match.get("label", "") or "").strip(),
                    "x0": float(match.get("x0", 0.0) or 0.0),
                    "x1": float(match.get("x1", 0.0) or 0.0),
                    "top": float(match.get("top", 0.0) or 0.0),
                    "bottom": float(match.get("bottom", 0.0) or 0.0),
                    "doctop": float(match.get("top", 0.0) or 0.0),
                }
            )
        return header_words

    def _header_words_to_column_geometry(
        self,
        header_words: list[dict[str, Any]],
        matches: list[dict[str, Any]],
        page: Any,
    ) -> tuple[list[tuple[float, float, str]], list[float]]:
        page_left = float(
            getattr(page, "bbox", (0.0, 0.0, getattr(page, "width", 0.0), 0.0))[0]
            or 0.0
        )
        page_right = float(
            getattr(page, "bbox", (0.0, 0.0, getattr(page, "width", 0.0), 0.0))[2]
            or getattr(page, "width", 0.0)
            or 0.0
        )
        sorted_words = sorted(header_words, key=lambda word: (float(word.get("x0", 0.0) or 0.0), float(word.get("x1", 0.0) or 0.0)))
        sorted_matches = sorted(matches, key=lambda match: (float(match["x0"]), float(match["x1"])))
        if len(sorted_words) != len(sorted_matches):
            sorted_words = self._matches_to_header_words(sorted_matches)
        vertical_lines: list[float] = [page_left]
        for index in range(len(sorted_words) - 1):
            current_right = float(sorted_words[index].get("x1", 0.0) or 0.0)
            next_left = float(sorted_words[index + 1].get("x0", 0.0) or 0.0)
            separator = (current_right + next_left) / 2.0
            vertical_lines.append(separator)
        vertical_lines.append(page_right)
        deduped_lines: list[float] = []
        for line in vertical_lines:
            if not deduped_lines or abs(line - deduped_lines[-1]) > 0.5:
                deduped_lines.append(line)
        bounds: list[tuple[float, float, str]] = []
        for index, match in enumerate(sorted_matches):
            if index + 1 >= len(deduped_lines):
                break
            left = float(deduped_lines[index])
            right = float(deduped_lines[index + 1])
            bounds.append((left, max(left, right), match["label"]))
        return bounds, deduped_lines

    def _extract_rows_by_pdfplumber_settings(
        self,
        page: Any,
        expected_headers: list[str],
        table_settings: dict[str, Any],
    ) -> list[list[str]]:
        extracted_tables = self._extract_pdfplumber_tables_from_page_with_settings(page, table_settings)
        normalized_expected = [normalize_header(header) for header in expected_headers]
        best_rows: list[list[str]] = []
        best_score = -1
        for extracted_rows in extracted_tables:
            normalized_rows = _normalize_extracted_rows(extracted_rows)
            if len(normalized_rows) < 2:
                continue
            candidate_headers = normalized_rows[0]
            candidate_score = sum(
                1
                for expected, candidate in zip(normalized_expected, [normalize_header(header) for header in candidate_headers])
                if expected and expected == candidate
            )
            if candidate_score > best_score:
                best_score = candidate_score
                best_rows = normalized_rows[1:]
                if candidate_score >= len(normalized_expected):
                    break
        return best_rows

    def _extract_rows_by_column_bounds(
        self,
        words: list[dict[str, Any]],
        header_words: list[dict[str, Any]],
        column_bounds: list[tuple[float, float, str]],
        options: ExtractionOptions,
    ) -> list[list[str]]:
        header_bottom = max(float(word.get("bottom", 0.0) or 0.0) for word in header_words)
        rows: list[list[str]] = []
        for line_words in self._group_pdfplumber_words_into_lines(words, options):
            if not line_words:
                continue
            line_top = min(float(word.get("top", 0.0) or 0.0) for word in line_words)
            if line_top <= header_bottom:
                continue
            row_values = [""] * len(column_bounds)
            for word in line_words:
                center = (float(word.get("x0", 0.0) or 0.0) + float(word.get("x1", 0.0) or 0.0)) / 2.0
                for column_index, (left, right, _label) in enumerate(column_bounds):
                    if center < left:
                        continue
                    if column_index + 1 == len(column_bounds):
                        in_column = center <= right
                    else:
                        in_column = center < right
                    if not in_column:
                        continue
                    text = str(word.get("text", "") or "").strip()
                    if not text:
                        break
                    row_values[column_index] = f"{row_values[column_index]} {text}".strip()
                    break
            if any(value.strip() for value in row_values):
                rows.append(row_values)
        return rows

    @staticmethod
    def _pdfplumber_schema_rescan_table_settings(
        page: Any,
        table: ExtractedTable,
        options: ExtractionOptions,
        column_bounds: list[tuple[float, float, str]] | None = None,
        vertical_lines: list[float] | None = None,
    ) -> dict[str, Any]:
        settings = dict(_pdfplumber_table_settings(options) or {})
        bbox = getattr(
            page,
            "bbox",
            (0.0, 0.0, float(getattr(page, "width", 0.0) or 0.0), float(getattr(page, "height", 0.0) or 0.0)),
        )
        page_top = float(bbox[1] or 0.0)
        page_bottom = float(bbox[3] or 0.0)
        resolved_column_bounds = column_bounds if column_bounds is not None else table.extraction_column_bounds
        resolved_vertical_lines = list(vertical_lines or table.extraction_vertical_lines)
        if not resolved_vertical_lines:
            for left, _right, _label in resolved_column_bounds:
                resolved_vertical_lines.append(float(left))
            if resolved_column_bounds:
                resolved_vertical_lines.append(float(resolved_column_bounds[-1][1]))
        deduped_lines: list[float] = []
        for line in resolved_vertical_lines:
            if not deduped_lines or abs(line - deduped_lines[-1]) > 0.5:
                deduped_lines.append(line)
        settings["vertical_strategy"] = "explicit"        
        settings["explicit_vertical_lines"] = deduped_lines
        settings["explicit_horizontal_lines"] = [page_top, page_bottom]
        print(deduped_lines)
        return settings

    @staticmethod
    def _format_pdfplumber_settings_text(settings: dict[str, Any] | None) -> str:
        if settings is None:
            return "[pdfplumber defaults]"
        return json.dumps(settings, sort_keys=True)
