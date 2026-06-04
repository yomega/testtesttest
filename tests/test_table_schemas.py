import unittest
from pathlib import Path
from types import SimpleNamespace

from src.pdf_spec_app.app import App, TableRegionSelectorDialog, default_table_schemas
import src.pdf_spec_app.extractor as extractor_module
from src.pdf_spec_app.extractor import (
    DocumentExtractor,
    _describe_pdfplumber_revision_usage,
    _group_manual_table_regions_by_page,
    _infer_tables_from_text,
    _split_evaluation_warnings,
    _table_from_html,
)
from src.pdf_spec_app.models import (
    ExtractedTable,
    ExtractedSegment,
    ExtractionOptions,
    ManualTableRegion,
    PagePreviewImage,
    SourceDocument,
    SpecSection,
    SpecStatement,
    Specification,
    TableSchema,
)
from src.pdf_spec_app.pipeline import ProcessingPipeline
from src.pdf_spec_app.spec_builder import SpecificationBuilder
from src.pdf_spec_app.table_schemas import match_table_schema, rank_tables_by_schema, reflow_table_to_schema


class TableSchemaTests(unittest.TestCase):
    def test_default_table_schemas_include_partlist(self) -> None:
        schemas = default_table_schemas()

        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0].name, "partlist")
        self.assertEqual(schemas[0].columns, ["description", "pattern no.", "v3"])
        self.assertEqual(schemas[0].required_columns, ["description", "pattern no."])
        self.assertEqual(schemas[0].start_header, "description")
        self.assertEqual(schemas[0].end_header, "v3")

    def test_html_table_parser_extracts_headers_and_rows(self) -> None:
        html = """
        <table>
            <tr><th>Field Name</th><th>Data Type</th></tr>
            <tr><td>customer_id</td><td>uuid</td></tr>
        </table>
        """

        headers, rows = _table_from_html(html)

        self.assertEqual(headers, ["Field Name", "Data Type"])
        self.assertEqual(rows, [["customer_id", "uuid"]])

    def test_spire_evaluation_warning_is_removed_from_content_and_warnings(self) -> None:
        cleaned, warnings = _split_evaluation_warnings(
            "Evaluation Warning : The document was created with Spire.PDF for Python.\nActual content line"
        )

        self.assertEqual(cleaned, "Actual content line")
        self.assertEqual(warnings, [])

    def test_text_table_fallback_detects_consistent_columns(self) -> None:
        tables = _infer_tables_from_text(
            2,
            "Description  Pattern no.\nValve body  P-100\nSeal kit  P-101",
        )

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].headers, ["Description", "Pattern no."])
        self.assertEqual(tables[0].rows, [["Valve body", "P-100"], ["Seal kit", "P-101"]])
        self.assertEqual(tables[0].backend, "text_fallback")

    def test_text_table_fallback_keeps_shorter_following_rows_in_same_table(self) -> None:
        tables = _infer_tables_from_text(
            3,
            "x  y  z\n1  1  1\n2  3",
        )

        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].headers, ["x", "y", "z"])
        self.assertEqual(tables[0].rows, [["1", "1", "1"], ["2", "3"]])

    def test_text_table_fallback_splits_when_a_new_header_row_appears(self) -> None:
        tables = _infer_tables_from_text(
            4,
            "x  y  z\n1  1  1\n2  3\nname  qty  note\nvalve  2  spare",
        )

        self.assertEqual(len(tables), 2)
        self.assertEqual(tables[0].headers, ["x", "y", "z"])
        self.assertEqual(tables[0].rows, [["1", "1", "1"], ["2", "3"]])
        self.assertEqual(tables[1].headers, ["name", "qty", "note"])
        self.assertEqual(tables[1].rows, [["valve", "2", "spare"]])

    def test_manual_table_regions_group_by_page(self) -> None:
        grouped = _group_manual_table_regions_by_page(
            [
                ManualTableRegion(page_number=2, left=10, top=10, right=20, bottom=20),
                ManualTableRegion(page_number=1, left=1, top=2, right=3, bottom=4),
                ManualTableRegion(page_number=2, left=30, top=30, right=40, bottom=40),
            ]
        )

        self.assertEqual(sorted(grouped.keys()), [1, 2])
        self.assertEqual(len(grouped[2]), 2)
        self.assertEqual(grouped[1][0].left, 1)

    def test_canvas_box_converts_to_manual_region_points(self) -> None:
        preview = PagePreviewImage(
            page_number=1,
            image_bytes=b"",
            image_width_px=1000,
            image_height_px=500,
            page_width_pts=200.0,
            page_height_pts=100.0,
        )

        left, top, right, bottom = TableRegionSelectorDialog._canvas_box_to_region(100, 50, 600, 250, preview)

        self.assertEqual((left, top, right, bottom), (20.0, 10.0, 120.0, 50.0))

    def test_spire_tables_inherit_full_page_source_text_for_schema_reflow(self) -> None:
        extractor = DocumentExtractor()
        source_document = SourceDocument(path=Path("sample.pdf"), title="sample")
        table = ExtractedTable(
            page_number=1,
            headers=['36"', '18"', '1 1/4"', "YT3618"],
            rows=[['42"', '18"', '1 1/4"', "YT4218"]],
            source_text='36" | 18" | 1 1/4" | YT3618',
            raw_text='36" | 18" | 1 1/4" | YT3618',
            backend="spire",
        )
        extractor._extract_spire_tables = lambda *_args: [table]  # type: ignore[method-assign]

        extractor._extract_local_table_fallbacks(
            source_document,
            table_extractor=None,
            page_total=1,
            page_text_by_number={1: "description w d h pattern no. v3"},
            evaluation_warnings=[],
        )

        self.assertEqual(len(source_document.tables), 1)
        self.assertEqual(source_document.tables[0].source_text, "description w d h pattern no. v3")
        self.assertEqual(source_document.tables[0].raw_text, '36" | 18" | 1 1/4" | YT3618')

    def test_disabled_ocr_returns_review_segments(self) -> None:
        segments = DocumentExtractor()._extract_pdf_pages_with_local_ocr(
            Path("sample.pdf"),
            [0, 2],
            "disabled",
            "eng",
            None,
        )

        self.assertEqual([segment.page_number for segment in segments], [1, 3])
        self.assertTrue(all(segment.segment_type == "ocr_disabled" for segment in segments))

    def test_disabled_full_document_ocr_returns_page_placeholders(self) -> None:
        original_pypdfium2 = extractor_module.pypdfium2

        class FakePdfDocument:
            def __init__(self, _path: str) -> None:
                self._length = 2

            def __len__(self) -> int:
                return self._length

            def close(self) -> None:
                return None

        extractor_module.pypdfium2 = SimpleNamespace(PdfDocument=FakePdfDocument)
        try:
            segments = DocumentExtractor()._extract_pdf_pages_with_local_ocr(
                Path("sample.pdf"),
                None,
                "disabled",
                "eng",
                None,
            )
        finally:
            extractor_module.pypdfium2 = original_pypdfium2

        self.assertEqual([segment.page_number for segment in segments], [1, 2])
        self.assertTrue(all(segment.segment_type == "ocr_disabled" for segment in segments))

    def test_extraction_options_can_use_ocr_only_mode(self) -> None:
        options = ExtractionOptions(ocr_backend="tesseract_only")

        self.assertEqual(options.ocr_backend, "tesseract_only")

    def test_preview_renders_ocr_only_warning(self) -> None:
        specification = Specification(
            title="Sample Specification",
            source_path=Path("sample.pdf"),
            preview_warnings=["OCR-only mode was used."],
            sections=[SpecSection(title="Functional Notes", statements=[SpecStatement(text="Real content")])],
        )

        preview = App._render_spec_preview(specification)

        self.assertIn("OCR-only mode was used.", preview)

    def test_power_query_formula_uses_pdf_tables(self) -> None:
        formula = DocumentExtractor._build_power_query_formula(Path(r"C:\docs\sample.pdf"))

        self.assertIn('Pdf.Tables(File.Contents("C:\\docs\\sample.pdf")', formula)
        self.assertIn('Implementation="1.3"', formula)
        self.assertIn("HeadersJson", formula)
        self.assertIn("JsonOutput", formula)

    def test_pdfplumber_backend_extracts_text_and_tables(self) -> None:
        original_pdfplumber = extractor_module.pdfplumber
        extract_tables_calls: list[object] = []

        class FakePdf:
            def __init__(self) -> None:
                self.pages = [
                    SimpleNamespace(
                        extract_text=lambda: "Description Pattern no.\nValve body P-100",
                        extract_tables=lambda *args, **kwargs: (
                            extract_tables_calls.append(kwargs.get("table_settings", args[0] if args else None))
                            or [[["Description", "Pattern no."], ["Valve body", "P-100"]]]
                        ),
                        find_tables=lambda *args, **kwargs: [],
                    )
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        extractor_module.pdfplumber = SimpleNamespace(open=lambda _path: FakePdf())
        try:
            document = DocumentExtractor().extract(
                "sample.pdf",
                ExtractionOptions(
                    table_extraction_backend="pdfplumber",
                    pdfplumber_vertical_strategy="text",
                    pdfplumber_horizontal_strategy="lines",
                    pdfplumber_text_x_tolerance=7,
                ),
            )
        finally:
            extractor_module.pdfplumber = original_pdfplumber

        self.assertEqual(document.segments[0].text, "Description Pattern no.\nValve body P-100")
        self.assertEqual(document.tables[0].backend, "pdfplumber")
        self.assertEqual(document.tables[0].headers, ["Description", "Pattern no."])
        self.assertEqual(document.tables[0].rows, [["Valve body", "P-100"]])
        self.assertTrue(extract_tables_calls)
        self.assertIsInstance(extract_tables_calls[0], dict)
        self.assertEqual(extract_tables_calls[0]["vertical_strategy"], "text")
        self.assertEqual(extract_tables_calls[0]["horizontal_strategy"], "lines")
        self.assertEqual(extract_tables_calls[0]["text_x_tolerance"], 7)

    def test_pdfplumber_backend_can_extract_tables_with_no_arguments(self) -> None:
        original_pdfplumber = extractor_module.pdfplumber
        extract_tables_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        class FakePdf:
            def __init__(self) -> None:
                self.pages = [
                    SimpleNamespace(
                        extract_text=lambda: "Description Pattern no.\nValve body P-100",
                        extract_tables=lambda *args, **kwargs: (
                            extract_tables_calls.append((args, kwargs))
                            or [[["Description", "Pattern no."], ["Valve body", "P-100"]]]
                        ),
                        find_tables=lambda *args, **kwargs: [],
                    )
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        extractor_module.pdfplumber = SimpleNamespace(open=lambda _path: FakePdf())
        try:
            DocumentExtractor().extract(
                "sample.pdf",
                ExtractionOptions(
                    table_extraction_backend="pdfplumber",
                    pdfplumber_use_default_table_settings=True,
                ),
            )
        finally:
            extractor_module.pdfplumber = original_pdfplumber

        self.assertTrue(extract_tables_calls)
        self.assertEqual(extract_tables_calls[0], ((), {}))

    def test_pdfplumber_revision_detection_prefers_latest_revision_chain(self) -> None:
        fake_pdf = SimpleNamespace(
            doc=SimpleNamespace(
                xrefs=[
                    SimpleNamespace(trailer={"Prev": 120}),
                    SimpleNamespace(trailer={}),
                ]
            )
        )

        description = _describe_pdfplumber_revision_usage(fake_pdf)

        self.assertEqual(description["pdf_revision_count"], "2")
        self.assertEqual(description["pdf_has_incremental_updates"], "True")
        self.assertEqual(
            description["pdf_revision_resolution"],
            "latest_revision_only_via_pdfminer_xref_chain",
        )

    def test_schema_match_prefers_required_columns(self) -> None:
        table = ExtractedTable(
            page_number=3,
            headers=["Field Name", "Data Type", "Required"],
            rows=[],
            confidence=0.8,
        )
        schemas = [
            TableSchema(
                name="Data Dictionary",
                columns=["Field Name", "Data Type", "Required"],
                required_columns=["Field Name", "Data Type"],
                weight=2.0,
            )
        ]

        result = match_table_schema(table, schemas)

        self.assertEqual(result.schema_name, "Data Dictionary")
        self.assertGreater(result.score, 1.0)

    def test_schema_score_increases_when_unknown_columns_fall_between_defined_headers(self) -> None:
        direct_table = ExtractedTable(
            page_number=1,
            headers=["Desc", "Code"],
            rows=[],
        )
        expanded_table = ExtractedTable(
            page_number=1,
            headers=["Desc", "W", "D", "H", "Code"],
            rows=[],
        )
        schema = TableSchema(
            name="Part List",
            columns=["Desc", "Code"],
            weight=2.0,
        )

        direct_match = match_table_schema(direct_table, [schema])
        expanded_match = match_table_schema(expanded_table, [schema])

        self.assertEqual(expanded_match.schema_name, "Part List")
        self.assertGreater(expanded_match.score, direct_match.score)

    def test_schema_can_match_start_and_end_only_definition(self) -> None:
        table = ExtractedTable(
            page_number=1,
            headers=["Description", "Pattern no."],
            rows=[["Valve body", "P-100"]],
        )
        schemas = [
            TableSchema(
                name="Part List",
                columns=[],
                start_header="Description",
                end_header="Pattern no.",
                weight=2.0,
            )
        ]

        result = match_table_schema(table, schemas)

        self.assertEqual(result.schema_name, "Part List")
        self.assertGreaterEqual(result.score, 2.0)

    def test_reflow_uses_start_and_end_headers_from_table_rows(self) -> None:
        table = ExtractedTable(
            page_number=2,
            headers=["Column1", "Column2", "Column3"],
            rows=[
                ["Description", "Pattern no."],
                ["Valve body", "P-100"],
                ["Seal kit", "P-101"],
            ],
            raw_text="Column1 | Column2 | Column3\nDescription | Pattern no.\nValve body | P-100\nSeal kit | P-101",
        )
        schema = TableSchema(
            name="Part List",
            columns=[],
            start_header="Description",
            end_header="Pattern no.",
        )

        reflowed = reflow_table_to_schema(table, schema)

        self.assertIsNotNone(reflowed)
        assert reflowed is not None
        self.assertEqual(reflowed.headers, ["Description", "Pattern no."])
        self.assertEqual(reflowed.rows, [["Valve body", "P-100"], ["Seal kit", "P-101"]])

    def test_rank_tables_promotes_row_with_single_required_header_over_default_headers(self) -> None:
        table = ExtractedTable(
            page_number=2,
            headers=["Column1", "Column2", "Column3"],
            rows=[
                ["Description", "Qty", "Notes"],
                ["Valve body", "2", "Primary"],
                ["Seal kit", "1", "Spare"],
            ],
            raw_text="Column1 | Column2 | Column3\nDescription | Qty | Notes\nValve body | 2 | Primary\nSeal kit | 1 | Spare",
        )
        schema = TableSchema(
            name="Parts",
            columns=["Description", "Pattern no."],
            required_columns=["Description"],
            weight=2.0,
        )

        ranked = rank_tables_by_schema([table], [schema])

        self.assertEqual(ranked[0].headers, ["Description", "Qty", "Notes"])
        self.assertEqual(ranked[0].rows, [["Valve body", "2", "Primary"], ["Seal kit", "1", "Spare"]])
        self.assertEqual(ranked[0].matched_schema, "Parts")

    def test_header_with_defined_endpoints_and_unknown_middle_columns_is_preferred(self) -> None:
        table = ExtractedTable(
            page_number=2,
            headers=["Column1", "Column2", "Column3", "Column4", "Column5"],
            rows=[
                ["Desc", "W", "D", "H", "Code"],
                ["Valve body", "10", "12", "4", "P-100"],
            ],
            raw_text="Column1 | Column2 | Column3 | Column4 | Column5\nDesc | W | D | H | Code\nValve body | 10 | 12 | 4 | P-100",
        )
        schema = TableSchema(
            name="Dimensions",
            columns=["Desc", "Code"],
            required_columns=["Desc"],
            weight=2.0,
        )

        ranked = rank_tables_by_schema([table], [schema])

        self.assertEqual(ranked[0].headers, ["Desc", "W", "D", "H", "Code"])
        self.assertEqual(ranked[0].matched_schema, "Dimensions")

    def test_non_required_schema_column_does_not_promote_header_row(self) -> None:
        table = ExtractedTable(
            page_number=2,
            headers=["Column1", "Column2", "Column3"],
            rows=[
                ["Qty", "Notes", "Extra"],
                ["2", "Primary", "A"],
            ],
            raw_text="Column1 | Column2 | Column3\nQty | Notes | Extra\n2 | Primary | A",
        )
        schema = TableSchema(
            name="Parts",
            columns=["Description", "Qty"],
            required_columns=["Description"],
            weight=2.0,
        )

        ranked = rank_tables_by_schema([table], [schema])

        self.assertEqual(ranked[0].headers, ["Column1", "Column2", "Column3"])
        self.assertIsNone(ranked[0].matched_schema)

    def test_rank_tables_reflows_using_surrounding_context(self) -> None:
        table = ExtractedTable(
            page_number=4,
            headers=["Column1", "Column2", "Column3", "Column4"],
            rows=[["A", "Valve body", "P-100", "Spare"], ["B", "Seal kit", "P-101", "Stock"]],
            raw_text="A | Valve body | P-100 | Spare\nB | Seal kit | P-101 | Stock",
            confidence=0.7,
        )
        schema = TableSchema(
            name="Part List",
            columns=[],
            start_header="Description",
            end_header="Pattern no.",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 4,
                    "text": "Section  Description  Pattern no.  Notes",
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["Description", "Pattern no."])
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100"], ["Seal kit", "P-101"]])
        self.assertEqual(ranked[0].matched_schema, "Part List")

    def test_context_search_uses_text_above_header_line_when_table_misses_schema(self) -> None:
        table = ExtractedTable(
            page_number=6,
            headers=["Column1", "Column2", "Column3", "Column4"],
            rows=[["A", "Valve body", "P-100", "OK"], ["B", "Seal kit", "P-101", "Low"]],
            raw_text="A | Valve body | P-100 | OK\nB | Seal kit | P-101 | Low",
        )
        schema = TableSchema(
            name="Part List",
            columns=["Description", "Pattern no.", "V3"],
            required_columns=["Description", "Pattern no."],
            start_header="Description",
            end_header="V3",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 6,
                    "text": "Parts overview\nDescription  Pattern no.  V3\nA  Valve body  P-100  OK\nB  Seal kit  P-101  Low",
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["Description", "Pattern no.", "V3"])
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100", "OK"], ["Seal kit", "P-101", "Low"]])

    def test_context_reflow_is_case_insensitive_and_updates_output_headers(self) -> None:
        table = ExtractedTable(
            page_number=7,
            headers=["COLUMN1", "COLUMN2", "COLUMN3", "COLUMN4"],
            rows=[["A", "Valve body", "P-100", "OK"], ["B", "Seal kit", "P-101", "Low"]],
            raw_text="A | Valve body | P-100 | OK\nB | Seal kit | P-101 | Low",
        )
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 7,
                    "text": "PARTS OVERVIEW\nDeScRiPtIoN  PATTERN NO.  v3\nA  Valve body  P-100  OK\nB  Seal kit  P-101  Low",
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["DeScRiPtIoN", "PATTERN NO.", "v3"])
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100", "OK"], ["Seal kit", "P-101", "Low"]])
        self.assertEqual(ranked[0].matched_schema, "partlist")

    def test_source_text_is_considered_for_table_reflow_alongside_extracted_text(self) -> None:
        table = ExtractedTable(
            page_number=8,
            headers=["Column1", "Column2", "Column3", "Column4"],
            rows=[["x", "Valve body", "P-100", "OK"], ["y", "Seal kit", "P-101", "Low"]],
            source_text="Intro line\nDescription  Pattern no.  V3\nx  Valve body  P-100  OK\ny  Seal kit  P-101  Low",
            raw_text="x | Valve body | P-100 | OK\ny | Seal kit | P-101 | Low",
        )
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 8,
                    "text": "Unhelpful extracted text only",
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["Description", "Pattern no.", "V3"])
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100", "OK"], ["Seal kit", "P-101", "Low"]])
        self.assertEqual(ranked[0].matched_schema, "partlist")

    def test_compact_source_text_line_can_recover_partlist_headers(self) -> None:
        table = ExtractedTable(
            page_number=9,
            headers=['36"', '18"', '1 1/4"', 'YT3618', '$320.', '$685.', '$788.', '$1,067.'],
            rows=[
                ['42"', '18"', '1 1/4"', 'YT4218', '$370.', '$724.', '$832.', '$1,119.'],
                ['48"', '18"', '1 1/4"', 'YT4818', '$415.', '$751.', '$864.', '$1,168.'],
            ],
            raw_text='36" | 18" | 1 1/4" | YT3618 | $320. | $685. | $788. | $1,067.\n42" | 18" | 1 1/4" | YT4218 | $370. | $724. | $832. | $1,119.',
        )
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 9,
                    "text": '18" and 24" Deep Rectangular description w d h pattern no. Laminate M/V1 V2 V3 (L) (V) (V) (V)\nAntenna Tops, 18" Deep 30" 18" 1 1/4" YT3018 $287. $650. $747. $1,011.',
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers[0], "description")
        self.assertEqual(ranked[0].headers[-1], "V3")
        self.assertIn("pattern no.", ranked[0].headers)
        self.assertEqual(ranked[0].matched_schema, "partlist")

    def test_reflow_inserts_blank_cells_by_comparing_with_previous_row_shape(self) -> None:
        table = ExtractedTable(
            page_number=10,
            headers=["Column1", "Column2", "Column3", "Column4", "Column5", "Column6", "Column7", "Column8"],
            rows=[
                ['Antenna Tops, 18" Deep', '30"', '18"', '1 1/4"', "YT3018", "$287.", "$650.", "$1,011."],
                ['36"', '18"', '1 1/4"', "YT3618", "$320.", "$685.", "$1,067."],
            ],
            raw_text='Antenna Tops, 18" Deep | 30" | 18" | 1 1/4" | YT3018 | $287. | $650. | $1,011.\n36" | 18" | 1 1/4" | YT3618 | $320. | $685. | $1,067.',
            source_text='description w d h pattern no. v1 v2 v3\nAntenna Tops, 18" Deep 30" 18" 1 1/4" YT3018 $287. $650. $1,011.',
        )
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )

        ranked = rank_tables_by_schema([table], [schema])

        self.assertEqual(ranked[0].headers, ["description", "w", "d", "h", "pattern no.", "v1", "v2", "v3"])
        self.assertEqual(
            ranked[0].rows,
            [
                ['Antenna Tops, 18" Deep', '30"', '18"', '1 1/4"', "YT3018", "$287.", "$650.", "$1,011."],
                ["", '36"', '18"', '1 1/4"', "YT3618", "$320.", "$685.", "$1,067."],
            ],
        )
        self.assertEqual(ranked[0].matched_schema, "partlist")

    def test_reflow_prefers_candidate_that_retains_more_nonblank_table_content(self) -> None:
        table = ExtractedTable(
            page_number=11,
            headers=['36"', '18"', '1 1/4"', 'YT3618', '$320.', '$685.', '$788.', '$1,067.'],
            rows=[
                ['42"', '18"', '1 1/4"', 'YT4218', '$370.', '$724.', '$832.', '$1,119.'],
            ],
            raw_text='36" | 18" | 1 1/4" | YT3618 | $320. | $685. | $788. | $1,067.\n42" | 18" | 1 1/4" | YT4218 | $370. | $724. | $832. | $1,119.',
        )
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 11,
                    "text": '18" and 24" Deep Rectangular description w d h pattern no. Laminate M/V1 V2 V3 (L) (V) (V) (V)',
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["description", "w", "d", "h", "pattern no.", "Laminate", "M/V1", "V2", "V3"])
        self.assertEqual(ranked[0].rows[0][0], "")
        self.assertEqual(ranked[0].rows[0][1:5], ['36"', '18"', '1 1/4"', 'YT3618'])
        self.assertEqual(ranked[0].rows[0][-4:], ['$320.', '$685.', '$788.', '$1,067.'])

    def test_rank_tables_merges_adjacent_same_schema_same_header_fragments(self) -> None:
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        left = ExtractedTable(
            page_number=12,
            headers=["Description", "Pattern no.", "V3"],
            rows=[["Valve body", "P-100", "OK"]],
            raw_text="Description | Pattern no. | V3\nValve body | P-100 | OK",
            backend="text_fallback",
            header_source="source_text:table_data",
            matched_schema="partlist",
            schema_score=2.9,
        )
        right = ExtractedTable(
            page_number=12,
            headers=["Description", "Pattern no.", "V3"],
            rows=[["", "Seal kit", "P-101"], ["", "Bracket", "P-102"]],
            raw_text="Description | Pattern no. | V3\n | Seal kit | P-101\n | Bracket | P-102",
            backend="text_fallback",
            header_source="source_text:table_data",
            matched_schema="partlist",
            schema_score=2.9,
        )

        ranked = rank_tables_by_schema([left, right], [schema])

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0].headers, ["Description", "Pattern no.", "V3"])
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100", "OK"], ["", "Seal kit", "P-101"], ["", "Bracket", "P-102"]])

    def test_rank_tables_does_not_merge_distinct_full_tables_with_same_schema(self) -> None:
        schema = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        left = ExtractedTable(
            page_number=13,
            headers=["Description", "Pattern no.", "V3"],
            rows=[["Valve body", "P-100", "OK"]],
            raw_text="Description | Pattern no. | V3\nValve body | P-100 | OK",
            backend="text_fallback",
            header_source="source_text",
            matched_schema="partlist",
            schema_score=2.9,
        )
        right = ExtractedTable(
            page_number=13,
            headers=["Description", "Pattern no.", "V3"],
            rows=[["Bracket", "P-200", "Stock"]],
            raw_text="Description | Pattern no. | V3\nBracket | P-200 | Stock",
            backend="text_fallback",
            header_source="source_text",
            matched_schema="partlist",
            schema_score=2.9,
        )

        ranked = rank_tables_by_schema([left, right], [schema])

        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0].rows, [["Valve body", "P-100", "OK"]])
        self.assertEqual(ranked[1].rows, [["Bracket", "P-200", "Stock"]])

    def test_rank_tables_does_not_merge_when_import_headers_already_match_a_schema(self) -> None:
        partlist = TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
            weight=1.8,
        )
        pricing = TableSchema(
            name="pricing",
            columns=["width", "depth", "price"],
            required_columns=["width", "price"],
            weight=1.8,
        )
        left = ExtractedTable(
            page_number=14,
            headers=["Description", "Pattern no.", "V3"],
            import_headers=["36\"", "18\"", "YT3618"],
            rows=[["Valve body", "P-100", "OK"]],
            raw_text="Description | Pattern no. | V3\nValve body | P-100 | OK",
            backend="text_fallback",
            header_source="source_text:table_data",
            matched_schema="partlist",
            schema_score=2.9,
        )
        right = ExtractedTable(
            page_number=14,
            headers=["Description", "Pattern no.", "V3"],
            import_headers=["Width", "Depth", "Price"],
            rows=[["", "24", "$100"]],
            raw_text="Description | Pattern no. | V3\n | 24 | $100",
            backend="text_fallback",
            header_source="source_text:table_data",
            matched_schema="partlist",
            schema_score=2.9,
        )

        ranked = rank_tables_by_schema([left, right], [partlist, pricing])

        self.assertEqual(len(ranked), 2)

    def test_context_search_only_runs_after_direct_schema_miss(self) -> None:
        table = ExtractedTable(
            page_number=5,
            headers=["Description", "Qty"],
            rows=[["Valve body", "2"]],
            raw_text="Description | Qty\nValve body | 2",
        )
        schema = TableSchema(
            name="Parts",
            columns=["Description"],
            weight=2.0,
        )
        segments = [
            type(
                "Segment",
                (),
                {
                    "page_number": 5,
                    "text": "Alt Header  Pattern no.  Notes",
                },
            )()
        ]

        ranked = rank_tables_by_schema([table], [schema], segments)

        self.assertEqual(ranked[0].headers, ["Description", "Qty"])
        self.assertEqual(ranked[0].rows, [["Valve body", "2"]])

    def test_rank_tables_sorts_schema_matches_first(self) -> None:
        matched = ExtractedTable(page_number=1, headers=["Endpoint", "Method"], rows=[], confidence=0.7)
        unmatched = ExtractedTable(page_number=2, headers=["Random", "Values"], rows=[], confidence=0.95)
        schema = TableSchema(name="API Matrix", columns=["Endpoint", "Method"], weight=1.8)

        ranked = rank_tables_by_schema([unmatched, matched], [schema])

        self.assertEqual(ranked[0].headers, ["Endpoint", "Method"])
        self.assertEqual(ranked[0].matched_schema, "API Matrix")

    def test_pipeline_reports_progress(self) -> None:
        class StubExtractor:
            def extract(self, file_path, options=None, progress_callback=None):
                if progress_callback is not None:
                    progress_callback(25.0, "extracting")
                self.options = options
                return type(
                    "Document",
                    (),
                    {
                        "tables": [],
                        "segments": [],
                        "path": file_path,
                        "title": "Sample",
                        "evaluation_warnings": [],
                    },
                )()

        class StubBuilder:
            def build(self, document):
                return "specification"

        updates: list[tuple[float, str]] = []
        extractor = StubExtractor()
        pipeline = ProcessingPipeline(
            extractor=extractor,
            builder=StubBuilder(),
            exporter=None,
        )
        options = ExtractionOptions(
            extract_tables=True,
            table_extraction_backend="spire",
            ocr_backend="tesseract",
            ocr_language="eng",
        )

        result = pipeline.process(
            "sample.pdf",
            extraction_options=options,
            progress_callback=lambda percent, message: updates.append((percent, message)),
        )

        self.assertEqual(result, "specification")
        self.assertEqual(extractor.options, options)
        self.assertIsNotNone(pipeline.last_document)
        self.assertEqual(updates[0], (0.0, "Starting specification generation..."))
        self.assertIn((80.0, "Ranking detected tables..."), updates)
        self.assertEqual(updates[-1], (100.0, "Specification generated."))

    def test_preview_renders_evaluation_warnings_separately(self) -> None:
        specification = Specification(
            title="Sample Specification",
            source_path=Path("sample.pdf"),
            preview_warnings=["Evaluation Warning : Demo license."],
            sections=[SpecSection(title="Functional Notes", statements=[SpecStatement(text="Real content")])],
        )

        preview = App._render_spec_preview(specification)

        self.assertIn("Evaluation Warnings", preview)
        self.assertIn("Real content", preview)

    def test_spec_builder_keeps_full_segment_text_without_truncation(self) -> None:
        segment_one_text = "Alpha " * 120
        segment_two_text = "Omega " * 120
        document = SourceDocument(
            path=Path("sample.pdf"),
            title="Sample",
            segments=[
                ExtractedSegment(page_number=1, text=segment_one_text.strip(), confidence=0.9),
                ExtractedSegment(page_number=2, text=segment_two_text.strip(), confidence=0.85),
            ],
        )

        specification = SpecificationBuilder().build(document)
        preview = App._render_spec_preview(specification)

        self.assertIn(segment_one_text.strip(), preview)
        self.assertIn(segment_two_text.strip(), preview)
        functional_notes = next(section for section in specification.sections if section.title == "Functional Notes")
        self.assertEqual(len(functional_notes.statements), 2)

    def test_document_summary_reports_structure_metrics_instead_of_raw_text(self) -> None:
        raw_text = (
            "1. Overview\n\n"
            "SYSTEM REQUIREMENTS\n\n"
            "This document describes the valve control workflow.\n\n"
            "Installation Notes\n\n"
            "Additional operational detail is captured here."
        )
        document = SourceDocument(
            path=Path("sample.pdf"),
            title="Sample",
            raw_import_text=raw_text,
            segments=[
                ExtractedSegment(page_number=1, text=raw_text, confidence=0.95, segment_type="pdf_text"),
            ],
        )

        specification = SpecificationBuilder().build(document)
        summary_section = next(section for section in specification.sections if section.title == "Document Summary")
        summary_text = summary_section.statements[0].text

        self.assertIn("page(s)", summary_text)
        self.assertIn("word(s)", summary_text)
        self.assertIn("paragraph block(s)", summary_text)
        self.assertIn("header-like line(s)", summary_text)
        self.assertNotIn("This document describes the valve control workflow.", summary_text)

    def test_processed_tables_debug_renders_extracted_tables(self) -> None:
        source_document = type(
            "Document",
            (),
            {
                "title": "Sample",
                "path": Path("sample.pdf"),
                "raw_tables": [],
                "evaluation_warnings": ["Evaluation Warning : Demo license."],
                "tables": [
                    ExtractedTable(
                        page_number=3,
                        headers=["Description", "Pattern no."],
                        rows=[["Valve body", "P-100"]],
                        raw_text="Description | Pattern no.\nValve body | P-100",
                        confidence=0.88,
                        backend="power_query",
                        matched_schema="partlist",
                        schema_score=1.5,
                    )
                ],
            },
        )()

        debug_text = App._render_table_debug(source_document, processed=True)

        self.assertIn("Detected tables: 1", debug_text)
        self.assertIn("Backend: power_query", debug_text)
        self.assertIn("Schema match: partlist", debug_text)
        self.assertIn("Valve body", debug_text)


if __name__ == "__main__":
    unittest.main()
