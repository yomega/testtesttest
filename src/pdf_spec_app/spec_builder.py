from __future__ import annotations

import re

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
        all_text = document.raw_import_text or "\n\n".join(segment.text for segment in document.segments if segment.text)
        nonempty_lines = [line.strip() for line in all_text.splitlines() if line.strip()]
        paragraphs = [block.strip() for block in re.split(r"\n\s*\n", all_text) if block.strip()]
        page_refs = sorted(
            {
                *(segment.page_number for segment in document.segments),
                *(table.page_number for table in document.tables),
                *(table.page_number for table in document.raw_tables),
            }
        )
        word_count = len(re.findall(r"\S+", all_text))
        line_count = len(nonempty_lines)
        paragraph_count = len(paragraphs)
        header_like_count = sum(1 for line in nonempty_lines if self._looks_like_heading(line))
        numbered_section_count = sum(1 for line in nonempty_lines if re.match(r"^\d+(?:\.\d+)*[\).\s-]+\S", line))
        page_count = len(page_refs)
        segment_count = len(document.segments)
        table_count = len(document.tables)

        text = (
            "Imported document structure summary: "
            f"{page_count} page(s), {word_count} word(s), {paragraph_count} paragraph block(s), "
            f"{line_count} non-empty line(s), {segment_count} extracted text segment(s), "
            f"{table_count} detected table(s), approximately {header_like_count} header-like line(s), "
            f"and approximately {numbered_section_count} numbered section marker(s)."
        )
        evidence = [
            EvidenceItem(
                page_number=page_refs[0] if page_refs else 1,
                excerpt=(
                    f"Pages: {page_refs or [1]}; "
                    f"Words: {word_count}; "
                    f"Paragraphs: {paragraph_count}; "
                    f"Lines: {line_count}; "
                    f"Text segments: {segment_count}; "
                    f"Tables: {table_count}"
                ),
                confidence=0.95,
                source_type="document_metrics",
            ),
            EvidenceItem(
                page_number=page_refs[0] if page_refs else 1,
                excerpt=(
                    f"Header-like lines (heuristic): {header_like_count}; "
                    f"Numbered section markers (heuristic): {numbered_section_count}"
                ),
                confidence=0.7,
                source_type="document_structure",
            ),
        ]
        return SpecStatement(text=text, evidence=evidence, confidence=0.95)

    def _build_requirement_candidates(self, document: SourceDocument) -> list[SpecStatement]:
        statements: list[SpecStatement] = []
        for segment in document.segments:
            cleaned = " ".join(segment.text.split())
            if not cleaned:
                continue
            text = f"Source text captured from page {segment.page_number}: {cleaned}"
            statements.append(
                SpecStatement(
                    text=text,
                    evidence=[
                        EvidenceItem(
                            page_number=segment.page_number,
                            excerpt=cleaned,
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

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if len(stripped) > 120:
            return False
        if re.match(r"^\d+(?:\.\d+)*[\).\s-]+\S", stripped):
            return True
        letters = [character for character in stripped if character.isalpha()]
        uppercase_ratio = (
            sum(1 for character in letters if character.isupper()) / len(letters)
            if letters
            else 0.0
        )
        if uppercase_ratio >= 0.8 and len(stripped.split()) <= 12:
            return True
        title_case_words = [
            word
            for word in re.split(r"\s+", stripped)
            if word and any(character.isalpha() for character in word)
        ]
        if title_case_words and len(title_case_words) <= 10:
            capitalized = sum(1 for word in title_case_words if word[:1].isupper())
            if capitalized / len(title_case_words) >= 0.8:
                return True
        return False
