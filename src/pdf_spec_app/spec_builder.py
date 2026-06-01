from __future__ import annotations

from .models import EvidenceItem, SourceDocument, SpecSection, SpecStatement, Specification


class SpecificationBuilder:
    """Build a cautious, evidence-backed specification from extracted content."""

    def build(self, document: SourceDocument) -> Specification:
        summary_statement = self._build_summary(document)
        requirements_statements = self._build_requirement_candidates(document)
        table_statements = self._build_table_summary(document)

        sections = [
            SpecSection(title="Document Summary", statements=[summary_statement]),
            SpecSection(title="Functional Notes", statements=requirements_statements),
            SpecSection(title="Detected Tables", statements=table_statements),
            SpecSection(title="Open Questions", statements=self._build_open_questions(document)),
        ]
        return Specification(
            title=f"{document.title} Specification",
            source_path=document.path,
            sections=sections,
            preview_warnings=list(document.evaluation_warnings),
        )

    def _build_summary(self, document: SourceDocument) -> SpecStatement:
        segment_count = len(document.segments)
        page_refs = sorted({segment.page_number for segment in document.segments})
        text = f"Imported document contains {segment_count} extracted text segments across pages {page_refs}."
        evidence = [
            EvidenceItem(
                page_number=segment.page_number,
                excerpt=segment.text[:280],
                confidence=segment.confidence,
                source_type=segment.segment_type,
            )
            for segment in document.segments[:3]
        ]
        return SpecStatement(text=text, evidence=evidence, confidence=0.95)

    def _build_requirement_candidates(self, document: SourceDocument) -> list[SpecStatement]:
        statements: list[SpecStatement] = []
        for segment in document.segments[:10]:
            cleaned = " ".join(segment.text.split())
            if not cleaned:
                continue
            text = f"Source text captured from page {segment.page_number}: {cleaned[:400]}"
            statements.append(
                SpecStatement(
                    text=text,
                    evidence=[
                        EvidenceItem(
                            page_number=segment.page_number,
                            excerpt=cleaned[:400],
                            confidence=segment.confidence,
                            source_type=segment.segment_type,
                        )
                    ],
                    confidence=segment.confidence,
                    status="supported" if segment.confidence >= 0.75 else "review",
                )
            )
        if not statements:
            statements.append(
                SpecStatement(
                    text="No usable text was extracted from the source document.",
                    confidence=0.0,
                    status="review",
                )
            )
        return statements

    def _build_table_summary(self, document: SourceDocument) -> list[SpecStatement]:
        if not document.tables:
            return [
                SpecStatement(
                    text="No tables were extracted from the source document. Review the PDF layout and define expected schemas if table structure is important.",
                    confidence=0.0,
                    status="review",
                )
            ]

        statements: list[SpecStatement] = []
        for table in document.tables:
            schema_text = table.matched_schema or "No schema match"
            statements.append(
                SpecStatement(
                    text=(
                        f"Table on page {table.page_number} has headers {table.headers or ['Unknown']}. "
                        f"Schema match: {schema_text}. Score: {table.schema_score}."
                    ),
                    evidence=[
                        EvidenceItem(
                            page_number=table.page_number,
                            excerpt=table.raw_text or ", ".join(table.headers),
                            confidence=table.confidence,
                            source_type="table",
                        )
                    ],
                    confidence=table.confidence,
                    status="supported" if table.confidence >= 0.75 else "review",
                )
            )
        return statements

    def _build_open_questions(self, document: SourceDocument) -> list[SpecStatement]:
        questions: list[SpecStatement] = []
        if any(segment.segment_type == "ocr_required" for segment in document.segments):
            questions.append(
                SpecStatement(
                    text="Some pages require OCR before the specification can be considered complete.",
                    confidence=0.2,
                    status="review",
                )
            )
        if not document.tables:
            questions.append(
                SpecStatement(
                    text="If the source contains structured tables, review whether the detected layout was machine-readable and define expected schemas for higher accuracy.",
                    confidence=0.4,
                    status="review",
                )
            )
        if not questions:
            questions.append(
                SpecStatement(
                    text="No immediate extraction gaps were detected by the bootstrap pipeline.",
                    confidence=0.6,
                    status="supported",
                )
            )
        return questions
