from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from .docx_exporter import DocxExporter
from .extractor import DocumentExtractor
from .models import ExtractionOptions, SourceDocument, Specification, TableSchema
from .spec_builder import SpecificationBuilder
from .table_schemas import rank_tables_by_schema

ProgressCallback = Callable[[float, str], None]


class ProcessingPipeline:
    def __init__(
        self,
        extractor: DocumentExtractor | None = None,
        builder: SpecificationBuilder | None = None,
        exporter: DocxExporter | None = None,
    ) -> None:
        self.extractor = extractor or DocumentExtractor()
        self.builder = builder or SpecificationBuilder()
        self.exporter = exporter or DocxExporter()
        self.last_document: SourceDocument | None = None

    def process(
        self,
        file_path: str | Path,
        table_schemas: list[TableSchema] | None = None,
        extraction_options: ExtractionOptions | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> Specification:
        self._report(progress_callback, 0.0, "Starting specification generation...")
        document = self.extractor.extract(file_path, extraction_options, progress_callback)
        self.last_document = document
        schemas = table_schemas or []
        document.raw_tables = deepcopy(document.tables)
        self._report(progress_callback, 80.0, "Ranking detected tables...")
        document.tables = rank_tables_by_schema(document.tables, schemas, document.segments)
        self._report(progress_callback, 90.0, "Building specification draft...")
        specification = self.builder.build(document)
        self._report(progress_callback, 100.0, "Specification generated.")
        return specification

    def export(self, specification: Specification, destination: str | Path) -> Path:
        return self.exporter.export(specification, destination)

    @staticmethod
    def _report(
        progress_callback: ProgressCallback | None,
        percent: float,
        message: str,
    ) -> None:
        if progress_callback is not None:
            progress_callback(percent, message)
