from __future__ import annotations

import json
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


class PdfPlumberBackendMixin:
    def generate_pdfplumber_debug_images(
        self,
        file_path: str | Path,
        options: ExtractionOptions | None = None,
    ) -> list[tuple[int, bytes, str]]:
        options = options or ExtractionOptions()
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            return []
        pdfplumber = self._pdfplumber_module()
        if pdfplumber is None:
            raise ExtractionError("pdfplumber is not installed. Install project dependencies first.")

        debug_images: list[tuple[int, bytes, str]] = []
        manual_regions_by_page = _group_manual_table_regions_by_page(options.manual_table_regions)
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_index, page in enumerate(pdf.pages):
                    page_number = page_index + 1
                    effective_page = self._dedupe_pdfplumber_page(page)
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
                        raw_page_text = effective_page.extract_text(layout=False) or ""
                    except TypeError:
                        raw_page_text = effective_page.extract_text() or ""
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
                    source_document.pdfplumber_debug_images.extend(
                        self._capture_pdfplumber_debug_tablefinder_images(
                            effective_page,
                            page_number,
                            options,
                            page_regions,
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
                            page_tables.extend(
                                self._build_pdfplumber_tables_from_rows(
                                    self._extract_pdfplumber_tables_from_page(effective_page, options),
                                    page_number,
                                    raw_page_text,
                                    backend="pdfplumber",
                                    extraction_box=self._page_box_tuple(page),
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
    ) -> list[tuple[int, bytes, str]]:
        if not regions:
            debug_png = self._capture_pdfplumber_debug_tablefinder(page, options)
            return [(page_number, debug_png, f"Page {page_number}")] if debug_png is not None else []

        debug_images: list[tuple[int, bytes, str]] = []
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
                debug_images.append((page_number, debug_png, self._manual_region_debug_label(page_number, region, index)))
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
                    extraction_box=extraction_box,
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
                cropped_text = cropped_page.extract_text(layout=False) or page_source_text
            except TypeError:
                cropped_text = cropped_page.extract_text() or page_source_text
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
            )
            if not built_tables and cropped_text:
                built_tables = _infer_tables_from_text(page_number, cropped_text)
                for table in built_tables:
                    table.backend = "pdfplumber_region_text_fallback"
                    table.extraction_box = bbox
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
        os = 1
        settings["explicit_vertical_lines"] = [os, max(float(getattr(page, "width", 0.0)) - os, 0.0)]
        settings["explicit_horizontal_lines"] = [os, max(float(getattr(page, "height", 0.0)) - os, 0.0)]
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
