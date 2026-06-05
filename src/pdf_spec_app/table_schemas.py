from __future__ import annotations

import re
from dataclasses import dataclass, replace

from src.pdf_spec_app import extractor

from .models import ExtractedSegment, ExtractedTable, TableSchema


def _strip_pdf_cid_artifacts(value: str) -> str:
    stripped = re.sub(r"\(cid\s*:\s*\d+\)", " ", value, flags=re.IGNORECASE)
    stripped = re.sub(r"\bcid\s*[:#]?\s*\d+\b", " ", stripped, flags=re.IGNORECASE)
    return stripped


def normalize_header(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", _strip_pdf_cid_artifacts(value).casefold()).strip()
    return re.sub(r"\s+", " ", normalized)


@dataclass(slots=True)
class TableMatchResult:
    schema_name: str | None
    score: float
    matched_columns: list[str]


def _schema_columns(schema: TableSchema) -> list[str]:
    columns = list(schema.columns)
    for boundary in (schema.start_header, schema.end_header):
        if boundary and normalize_header(boundary) not in {normalize_header(column) for column in columns}:
            columns.append(boundary)
    return columns


def _schema_terms(schema: TableSchema) -> dict[str, set[str]]:
    terms: dict[str, set[str]] = {}
    for column in _schema_columns(schema):
        normalized = normalize_header(column)
        alias_values = schema.aliases.get(column, [])
        alias_set = {normalized, *(normalize_header(alias) for alias in alias_values)}
        terms[column] = alias_set
    return terms


def _matched_columns_for_row(row: list[str], schema: TableSchema) -> tuple[list[str], int]:
    matched_columns: list[str] = []
    required_hits = 0
    for column, aliases in _schema_terms(schema).items():
        if _find_alias_span(row, aliases) is not None:
            matched_columns.append(column)
            if column in schema.required_columns:
                required_hits += 1
    return matched_columns, required_hits


def _schema_reference_columns(schema: TableSchema, required_only: bool = False) -> list[str]:
    if required_only and schema.required_columns:
        return list(schema.required_columns)
    return _schema_columns(schema)


def _schema_terms_for_columns(schema: TableSchema, columns: list[str]) -> dict[str, set[str]]:
    terms = _schema_terms(schema)
    return {column: terms[column] for column in columns if column in terms}


def _row_contains_schema_signal(row: list[str], schema: TableSchema, required_only: bool = False) -> bool:
    reference_columns = _schema_reference_columns(schema, required_only=required_only)
    if not reference_columns:
        return False
    for aliases in _schema_terms_for_columns(schema, reference_columns).values():
        if _find_alias_span(row, aliases) is not None:
            return True
    return False


def _header_match_score(schema: TableSchema, row: list[str]) -> float:
    matched_columns, required_hits = _matched_columns_for_row(row, schema)
    schema_columns = _schema_columns(schema)
    if not matched_columns:
        return 0.0
    if schema.required_columns and required_hits < len(schema.required_columns):
        return 0.0
    base_ratio = len(matched_columns) / max(len(schema_columns), 1)
    weighted_score = base_ratio * schema.weight
    if required_hits:
        weighted_score += 0.25 * required_hits
    weighted_score += _in_between_header_bonus(schema, row, matched_columns)
    weighted_score -= _outside_boundary_penalty(schema, row)
    return round(weighted_score, 4)


def _in_between_header_bonus(schema: TableSchema, row: list[str], matched_columns: list[str]) -> float:
    if len(matched_columns) < 2:
        return 0.0

    schema_terms = _schema_terms(schema)
    matched_positions: list[tuple[int, str]] = []
    seen_columns: set[str] = set()

    for column in matched_columns:
        if column in seen_columns:
            continue
        span = _find_alias_span(row, schema_terms.get(column, set()))
        if span is not None:
            matched_positions.append((span[0], column))
            seen_columns.add(column)

    if len(matched_positions) < 2:
        return 0.0

    ordered_matches = sorted(matched_positions, key=lambda item: item[0])
    bonus = 0.0
    for (left_index, _left_column), (right_index, _right_column) in zip(ordered_matches, ordered_matches[1:]):
        gap = right_index - left_index - 1
        if gap > 0:
            # Reward structurally plausible header spans that keep user-defined anchors in order
            # while allowing extra undocumented columns between them.
            bonus += min(0.4, 0.1 * gap)
    return bonus


def _outside_boundary_penalty(schema: TableSchema, row: list[str]) -> float:
    boundary_slice = _find_boundary_slice(row, schema)
    if boundary_slice is None:
        return 0.0
    start_index, end_index = boundary_slice
    extra_tokens = start_index + max(0, len(row) - end_index - 1)
    return min(1.0, 0.1 * extra_tokens)


def _tokenize_row(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*\|\s*|\t+|\s{2,}", text) if part.strip()]


def _compact_tokenize_row(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*\|\s*|\s+", text.strip()) if part.strip() and part.strip() != "|"]


def _row_candidates_from_text(text: str, source_name: str) -> list[tuple[str, list[str]]]:
    candidates: list[tuple[str, list[str]]] = []
    standard = _tokenize_row(text)
    if len(standard) >= 2:
        candidates.append((source_name, standard))
        return candidates

    compact = _compact_tokenize_row(text)
    if len(compact) >= 2:
        candidates.append((f"{source_name}:compact", compact))
    return candidates


def _row_streams_from_lines(lines: list[str], source_name: str) -> list[tuple[str, list[list[str]]]]:
    standard_rows: list[list[str]] = []
    compact_rows: list[list[str]] = []
    for line in lines:
        for candidate_name, candidate_row in _row_candidates_from_text(line, source_name):
            if candidate_name.endswith(":compact"):
                compact_rows.append(candidate_row)
            else:
                standard_rows.append(candidate_row)

    streams: list[tuple[str, list[list[str]]]] = []
    if standard_rows:
        streams.append((source_name, standard_rows))
    if compact_rows:
        streams.append((f"{source_name}:compact", compact_rows))
    return streams


def _whole_text_row_stream(text: str, source_name: str) -> tuple[str, list[list[str]]] | None:
    compact = _compact_tokenize_row(text)
    if len(compact) < 2:
        return None
    return (f"{source_name}:whole", [compact])


def _find_alias_span(row: list[str], aliases: set[str], max_span: int = 4) -> tuple[int, int] | None:
    normalized_row = [normalize_header(cell) for cell in row]
    for start_index in range(len(normalized_row)):
        parts: list[str] = []
        for end_index in range(start_index, min(len(normalized_row), start_index + max_span)):
            if not normalized_row[end_index]:
                break
            parts.append(normalized_row[end_index])
            if " ".join(parts) in aliases:
                return start_index, end_index
    return None


def _collapse_header_cells(row: list[str], start_index: int, end_index: int, schema: TableSchema) -> list[str]:
    aliases_by_column = _schema_terms(schema)
    headers: list[str] = []
    index = start_index
    while index <= end_index:
        best_span: tuple[int, int] | None = None
        for aliases in aliases_by_column.values():
            span = _find_alias_span(row[index : end_index + 1], aliases)
            if span is None or span[0] != 0:
                continue
            absolute_span = (span[0] + index, span[1] + index)
            if best_span is None or absolute_span[1] > best_span[1]:
                best_span = absolute_span
        if best_span is not None:
            headers.append(" ".join(row[best_span[0] : best_span[1] + 1]))
            index = best_span[1] + 1
            continue
        headers.append(row[index])
        index += 1
    return headers


def _table_row_sets(table: ExtractedTable) -> list[tuple[str, list[list[str]], int]]:
    row_sets: list[tuple[str, list[list[str]], int]] = []
    if table.headers:
        row_sets.append(("headers", [table.headers, *table.rows], 0))
    for index, row in enumerate(table.rows):
        row_sets.append((f"rows:{index}", table.rows[index:], 0))
    if table.source_text:
        whole_stream = _whole_text_row_stream(table.source_text, "source_text")
        if whole_stream is not None:
            row_sets.append((whole_stream[0], whole_stream[1], 0))
        for stream_name, source_rows in _row_streams_from_lines(table.source_text.splitlines(), "source_text"):
            row_sets.append((stream_name, source_rows, 0))
            for index in range(1, len(source_rows)):
                row_sets.append((f"{stream_name}:{index}", source_rows[index:], 0))
    if table.raw_text:
        whole_stream = _whole_text_row_stream(table.raw_text, "raw_text")
        if whole_stream is not None:
            row_sets.append((whole_stream[0], whole_stream[1], 0))
        for stream_name, raw_rows in _row_streams_from_lines(table.raw_text.splitlines(), "raw_text"):
            row_sets.append((stream_name, raw_rows, 0))
            for index in range(1, len(raw_rows)):
                row_sets.append((f"{stream_name}:{index}", raw_rows[index:], 0))
    return row_sets


def _context_row_sets(page_number: int, segments: list[ExtractedSegment]) -> list[tuple[str, list[list[str]], int]]:
    row_sets: list[tuple[str, list[list[str]], int]] = []
    for segment_index, segment in enumerate(segments):
        if segment.page_number != page_number:
            continue
        whole_stream = _whole_text_row_stream(segment.text, f"context:{segment_index}")
        if whole_stream is not None:
            row_sets.append((whole_stream[0], whole_stream[1], 0))
        for stream_name, rows in _row_streams_from_lines(segment.text.splitlines(), f"context:{segment_index}"):
            row_sets.append((stream_name, rows, 0))
            for index in range(1, len(rows)):
                row_sets.append((f"{stream_name}:{index}", rows[index:], 0))
    return row_sets


def _preferred_data_rows(table: ExtractedTable) -> list[list[str]]:
    if table.source_text:
        source_rows = [_tokenize_row(line) for line in table.source_text.splitlines()]
        source_rows = [row for row in source_rows if len(row) >= 2]
        if source_rows:
            return source_rows
    if table.raw_text:
        raw_rows = [_tokenize_row(line) for line in table.raw_text.splitlines()]
        raw_rows = [row for row in raw_rows if len(row) >= 2]
        if raw_rows:
            return raw_rows
    if table.headers:
        return [table.headers, *table.rows]
    return list(table.rows)


def _data_rows_without_default_header(table: ExtractedTable) -> list[list[str]]:
    if table.source_text:
        source_rows = [_tokenize_row(line) for line in table.source_text.splitlines()]
        source_rows = [row for row in source_rows if len(row) >= 2]
        if source_rows:
            return source_rows
    if table.raw_text:
        raw_rows = [_tokenize_row(line) for line in table.raw_text.splitlines()]
        raw_rows = [row for row in raw_rows if len(row) >= 2]
        if raw_rows:
            return raw_rows
    return list(table.rows)


def _looks_like_default_header_row(headers: list[str]) -> bool:
    if not headers:
        return True
    return all(re.fullmatch(r"column\d+", header.strip(), re.IGNORECASE) for header in headers if header.strip())


def _preserved_table_rows(table: ExtractedTable, schema: TableSchema) -> list[list[str]]:
    if _looks_like_default_header_row(table.headers):
        return list(table.rows)
    if match_table_schema(table, [schema]).score > 0.0:
        return list(table.rows)
    return [table.headers, *table.rows]


def _find_boundary_slice(
    row: list[str],
    schema: TableSchema,
) -> tuple[int, int] | None:
    if not schema.start_header or not schema.end_header:
        return None

    start_terms = _schema_terms(
        TableSchema(name=schema.name, columns=[], aliases=schema.aliases, start_header=schema.start_header)
    ).get(schema.start_header, {normalize_header(schema.start_header)})
    end_terms = _schema_terms(
        TableSchema(name=schema.name, columns=[], aliases=schema.aliases, end_header=schema.end_header)
    ).get(schema.end_header, {normalize_header(schema.end_header)})
    start_span = _find_alias_span(row, start_terms)
    if start_span is None:
        return None

    end_span: tuple[int, int] | None = None
    for offset in range(start_span[1] + 1, len(row)):
        candidate_span = _find_alias_span(row[offset:], end_terms)
        if candidate_span is not None:
            end_span = (candidate_span[0] + offset, candidate_span[1] + offset)
            break
    if end_span is None:
        end_span = _find_alias_span(row, end_terms)
    if end_span is None:
        return None

    start_index = start_span[0]
    end_index = end_span[1]
    if end_index < start_index:
        return None
    return start_index, end_index


def _slice_rows(rows: list[list[str]], start_index: int, end_index: int) -> list[list[str]]:
    width = end_index - start_index + 1
    sliced_rows: list[list[str]] = []
    for row in rows:
        if len(row) > end_index:
            sliced = row[start_index : end_index + 1]
        elif len(row) >= width:
            sliced = row[-width:]
        else:
            continue
        if any(cell.strip() for cell in sliced):
            sliced_rows.append(sliced)
    return sliced_rows


def _slice_rows_by_logical_columns(rows: list[list[str]], start_column: int, width: int) -> list[list[str]]:
    sliced_rows: list[list[str]] = []
    for row in rows:
        if len(row) >= start_column + width:
            sliced = row[start_column : start_column + width]
        elif len(row) >= width:
            sliced = row[-width:]
        else:
            continue
        if any(cell.strip() for cell in sliced):
            sliced_rows.append(sliced)
    return sliced_rows


def _logical_column_start(row: list[str], start_index: int, schema: TableSchema) -> int:
    if start_index <= 0:
        return 0
    return len(_collapse_header_cells(row, 0, start_index - 1, schema))


def _rebuild_raw_text(headers: list[str], rows: list[list[str]]) -> str:
    return extractor._form_markdown_table([headers, *rows])

def _find_best_partial_header_row(
    row_sets: list[tuple[str, list[list[str]], int]],
    schema: TableSchema,
    required_only: bool = False,
) -> tuple[str, list[list[str]], int, float] | None:
    best: tuple[str, list[list[str]], int, float] | None = None
    for source_name, row_set, header_index in row_sets:
        if not row_set:
            continue
        candidate_row = row_set[header_index]
        if not _row_contains_schema_signal(candidate_row, schema, required_only=required_only):
            continue
        score = _header_match_score(schema, candidate_row)
        if score <= 0.0 and not required_only:
            continue
        if score <= 0.0 and required_only:
            # A single required-column hit is only a weak hint; keep it eligible
            # without letting it outrank a row that actually matches the schema shape.
            score = 0.15
        if source_name.endswith(":compact") or ":compact:" in source_name:
            score -= 0.05
        if best is None or score > best[3]:
            best = (source_name, row_set, header_index, score)
    return best


def _iter_partial_header_rows(
    row_sets: list[tuple[str, list[list[str]], int]],
    schema: TableSchema,
    required_only: bool = False,
) -> list[tuple[str, list[list[str]], int, float]]:
    candidates: list[tuple[str, list[list[str]], int, float]] = []
    for source_name, row_set, header_index in row_sets:
        if not row_set:
            continue
        candidate_row = row_set[header_index]
        if not _row_contains_schema_signal(candidate_row, schema, required_only=required_only):
            continue
        matched_columns, _required_hits = _matched_columns_for_row(candidate_row, schema)
        boundary_slice = _find_boundary_slice(candidate_row, schema)
        if required_only and schema.start_header and schema.end_header:
            # For bounded schemas, a weak single-hit row is too noisy to consider.
            if boundary_slice is None and len(matched_columns) < 2:
                continue
        score = _header_match_score(schema, candidate_row)
        if score <= 0.0 and not required_only:
            continue
        if score <= 0.0 and required_only:
            score = 0.15
        if source_name.endswith(":compact") or ":compact:" in source_name:
            score -= 0.05
        candidates.append((source_name, row_set, header_index, score))
    return sorted(candidates, key=lambda item: item[3], reverse=True)


def _align_row_width(row: list[str], width: int) -> list[str] | None:
    if width <= 0:
        return None
    if len(row) == width:
        return row
    if len(row) > width:
        return row[-width:]
    return None


def _cell_shape(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return "blank"
    if normalized.startswith("$"):
        return "currency"
    if '"' in normalized or re.fullmatch(r"\d+(?:\s+\d+/\d+)?", normalized):
        return "dimension"
    if re.fullmatch(r"[A-Za-z]+[A-Za-z0-9./-]*\d+[A-Za-z0-9./-]*", normalized):
        return "code"
    if re.fullmatch(r"[\d,./-]+", normalized):
        return "numeric"
    if re.search(r"[A-Za-z]", normalized):
        return "text"
    return "other"


def _header_expected_shape(header: str) -> str:
    normalized = normalize_header(header)
    if not normalized:
        return "blank"
    if normalized in {"w", "d", "h", "width", "depth", "height", "dia", "diameter", "od", "id"}:
        return "dimension"
    if normalized.startswith("v") and normalized[1:].isdigit():
        return "currency"
    if "price" in normalized or "cost" in normalized or "laminate" in normalized or normalized.startswith("m v"):
        return "currency"
    if "pattern" in normalized or "code" in normalized or normalized.endswith("no"):
        return "code"
    if "description" in normalized or "name" in normalized or "item" in normalized:
        return "text"
    return "blank"


def _shape_similarity(value: str, reference: str) -> float:
    value_shape = _cell_shape(value)
    reference_shape = _cell_shape(reference)
    if value_shape == reference_shape:
        return 2.0
    compatible_shapes = {
        ("dimension", "numeric"),
        ("numeric", "dimension"),
        ("code", "text"),
        ("text", "code"),
    }
    if (value_shape, reference_shape) in compatible_shapes:
        return 1.0
    if reference_shape == "blank":
        return 0.25
    return -0.75


def _shape_similarity_to_expected(value: str, expected_shape: str) -> float:
    value_shape = _cell_shape(value)
    if value_shape == expected_shape:
        return 2.0
    compatible_shapes = {
        ("dimension", "numeric"),
        ("numeric", "dimension"),
        ("code", "text"),
        ("text", "code"),
    }
    if (value_shape, expected_shape) in compatible_shapes:
        return 1.0
    if expected_shape == "blank":
        return 0.2
    return -0.9


def _last_nonblank_row(rows: list[list[str]]) -> list[str] | None:
    for row in reversed(rows):
        if any(cell.strip() for cell in row):
            return row
    return None


def _align_row_using_reference(
    row: list[str],
    headers: list[str],
    reference_row: list[str] | None,
) -> list[str] | None:
    width = len(headers)
    if width <= 0:
        return None
    if not row:
        return None

    cells = [cell for cell in row if cell.strip()]
    if not cells:
        return None

    drop_penalty = -1.25
    blank_penalty = -0.4
    memo: dict[tuple[int, int], tuple[float, list[str]]] = {}

    def solve(cell_index: int, column_index: int) -> tuple[float, list[str]]:
        key = (cell_index, column_index)
        if key in memo:
            return memo[key]
        if column_index == width:
            if cell_index == len(cells):
                memo[key] = (0.0, [])
            else:
                memo[key] = (drop_penalty * (len(cells) - cell_index), [])
            return memo[key]
        if cell_index == len(cells):
            remaining = [""] * (width - column_index)
            memo[key] = (blank_penalty * (width - column_index), remaining)
            return memo[key]

        if reference_row is not None:
            reference_value = reference_row[column_index] if column_index < len(reference_row) else ""
            similarity = _shape_similarity(cells[cell_index], reference_value)
        else:
            similarity = _shape_similarity_to_expected(cells[cell_index], _header_expected_shape(headers[column_index]))

        assign_score, assign_tail = solve(cell_index + 1, column_index + 1)
        assign_score += similarity
        best_score = assign_score
        best_row = [cells[cell_index], *assign_tail]

        blank_score, blank_tail = solve(cell_index, column_index + 1)
        blank_score += blank_penalty
        if blank_score > best_score:
            best_score = blank_score
            best_row = ["", *blank_tail]

        drop_score, drop_tail = solve(cell_index + 1, column_index)
        drop_score += drop_penalty
        if drop_score > best_score:
            best_score = drop_score
            best_row = drop_tail

        memo[key] = (best_score, best_row)
        return memo[key]

    _score, aligned = solve(0, 0)
    if len(aligned) != width:
        return _align_row_width(row, width)
    return aligned


def _build_reflowed_table(
    table: ExtractedTable,
    headers: list[str],
    data_rows: list[list[str]],
    header_source: str,
) -> ExtractedTable | None:
    aligned_rows: list[list[str]] = []
    width = len(headers)
    for row in data_rows:
        reference_row = _last_nonblank_row(aligned_rows)
        aligned = _align_row_using_reference(row, headers, reference_row)
        if aligned and any(cell.strip() for cell in aligned):
            aligned_rows.append(aligned)
    if not headers or not aligned_rows:
        return None
    return replace(
        table,
        headers=headers,
        rows=aligned_rows,
        raw_text=_rebuild_raw_text(headers, aligned_rows),
        confidence=min(1.0, table.confidence + 0.05),
        header_source=header_source,
    )


def _build_header_only_reflowed_table(
    table: ExtractedTable,
    headers: list[str],
    header_source: str,
    data_rows: list[list[str]] | None = None,
) -> ExtractedTable | None:
    if not headers:
        return None
    rows = data_rows if data_rows else table.rows
    return replace(
        table,
        headers=headers,
        rows=rows,
        raw_text=extractor._form_markdown_table([headers, *rows]),
        confidence=min(1.0, table.confidence + 0.03),
        header_source=header_source,
    )


def _has_leading_stub_columns(headers: list[str], rows: list[list[str]]) -> bool:
    width = len(headers)
    return width > 0 and any(len(row) > width for row in rows)


def _nonblank_cell_count(rows: list[list[str]]) -> int:
    return sum(1 for row in rows for cell in row if cell.strip())


def _candidate_match_tuple(table: ExtractedTable, schema: TableSchema) -> tuple[float, float, int, int]:
    match = match_table_schema(table, [schema])
    return match.score, table.confidence, _nonblank_cell_count(table.rows), len(table.rows)


def _normalized_headers(headers: list[str]) -> list[str]:
    return [normalize_header(header) for header in headers]


def _first_nonblank_index(row: list[str]) -> int | None:
    for index, cell in enumerate(row):
        if cell.strip():
            return index
    return None


def _looks_like_continuation_fragment(table: ExtractedTable) -> bool:
    if not table.rows:
        return False
    first_row = table.rows[0]
    if not first_row:
        return False
    if first_row[0].strip() == "":
        return True
    first_value_index = _first_nonblank_index(first_row)
    if first_value_index is not None and first_value_index > 0:
        return True
    nonblank_cells = sum(1 for cell in first_row if cell.strip())
    return nonblank_cells < len(table.headers)


def _is_table_data_reflow(table: ExtractedTable) -> bool:
    return ":table_data" in (table.header_source or "")


def _has_direct_import_schema_match(table: ExtractedTable, schemas: list[TableSchema]) -> bool:
    import_headers = table.import_headers or table.headers
    if not import_headers:
        return False
    direct_match = match_table_schema(
        replace(
            table,
            headers=import_headers,
            import_headers=import_headers,
        ),
        schemas,
    )
    return direct_match.score > 0.0


def _can_merge_adjacent_tables(left: ExtractedTable, right: ExtractedTable, schemas: list[TableSchema]) -> bool:
    if left.page_number != right.page_number:
        return False
    if left.matched_schema != right.matched_schema:
        return False
    if left.backend != right.backend:
        return False
    if not left.headers or not right.headers:
        return False
    if _normalized_headers(left.headers) != _normalized_headers(right.headers):
        return False
    if not (_is_table_data_reflow(left) or _is_table_data_reflow(right)):
        return False
    if _has_direct_import_schema_match(right, schemas):
        return False
    return _looks_like_continuation_fragment(right)


def _merge_adjacent_tables(tables: list[ExtractedTable], schemas: list[TableSchema]) -> list[ExtractedTable]:
    if not tables:
        return []

    merged: list[ExtractedTable] = [tables[0]]
    for table in tables[1:]:
        previous = merged[-1]
        if not _can_merge_adjacent_tables(previous, table, schemas):
            merged.append(table)
            continue

        merged_rows = [*previous.rows, *table.rows]
        merged[-1] = replace(
            previous,
            rows=merged_rows,
            raw_text=_rebuild_raw_text(previous.headers, merged_rows),
            confidence=max(previous.confidence, table.confidence),
            schema_score=max(previous.schema_score, table.schema_score),
            schema_debug_notes=[
                *previous.schema_debug_notes,
                f"Merged with adjacent table on page {table.page_number} sharing headers {table.headers}.",
                *table.schema_debug_notes,
            ],
        )
    return merged


def _pick_better_candidate(
    current_best: ExtractedTable | None,
    candidate: ExtractedTable | None,
    schema: TableSchema,
) -> ExtractedTable | None:
    if candidate is None:
        return current_best
    if current_best is None:
        return candidate
    if _candidate_match_tuple(candidate, schema) > _candidate_match_tuple(current_best, schema):
        return candidate
    return current_best


def reflow_table_to_schema(
    table: ExtractedTable,
    schema: TableSchema,
    segments: list[ExtractedSegment] | None = None,
) -> ExtractedTable | None:
    best_candidate: ExtractedTable | None = None
    table_row_sets = _table_row_sets(table)
    direct_candidates = _iter_partial_header_rows(
        table_row_sets,
        schema,
        required_only=True,
    )
    for source_name, row_set, header_index, _score in direct_candidates:
        header_row = row_set[header_index]
        if schema.start_header and schema.end_header:
            boundary_slice = _find_boundary_slice(header_row, schema)
            if boundary_slice is not None:
                start_index, end_index = boundary_slice
                headers = _collapse_header_cells(header_row, start_index, end_index, schema)
                data_source = row_set[header_index + 1 :]
                logical_start = _logical_column_start(header_row, start_index, schema)
                logical_width = len(headers)
                if source_name.startswith("source_text:") or source_name == "source_text":
                    preserved_rows = _preserved_table_rows(table, schema)
                    if start_index == 0 and _has_leading_stub_columns(headers, data_source):
                        reflowed = _build_reflowed_table(table, headers, data_source, source_name)
                    else:
                        sliced_data_rows = _slice_rows_by_logical_columns(data_source, logical_start, logical_width)
                        reflowed = _build_reflowed_table(table, headers, sliced_data_rows, source_name)
                        if reflowed is None:
                            reflowed = _build_reflowed_table(table, headers, data_source, source_name)
                        if reflowed is None and source_name.endswith(":compact"):
                            reflowed = _build_header_only_reflowed_table(table, headers, source_name)
                    best_candidate = _pick_better_candidate(best_candidate, reflowed, schema)
                    preserved_reflowed = _build_reflowed_table(table, headers, preserved_rows, f"{source_name}:table_data")
                    best_candidate = _pick_better_candidate(best_candidate, preserved_reflowed, schema)
                data_rows = _slice_rows_by_logical_columns(data_source, logical_start, logical_width)
                reflowed = _build_reflowed_table(table, headers, data_rows, source_name)
                if reflowed is None and source_name.endswith(":compact"):
                    reflowed = _build_header_only_reflowed_table(table, headers, source_name)
                best_candidate = _pick_better_candidate(best_candidate, reflowed, schema)
        reflowed = _build_reflowed_table(table, header_row, row_set[header_index + 1 :], source_name)
        if reflowed is None and source_name.endswith(":compact"):
            reflowed = _build_header_only_reflowed_table(table, header_row, source_name)
        best_candidate = _pick_better_candidate(best_candidate, reflowed, schema)

    if match_table_schema(table, [schema]).score > 0.0 and best_candidate is None:
        return None

    context_candidates = _iter_partial_header_rows(
        _context_row_sets(table.page_number, segments or []),
        schema,
        required_only=False,
    )
    for _source_name, row_set, header_index, _score in context_candidates:
        header_row = row_set[header_index]
        data_rows = _data_rows_without_default_header(table)
        preserved_rows = _preserved_table_rows(table, schema)
        if schema.start_header and schema.end_header:
            boundary_slice = _find_boundary_slice(header_row, schema)
            if boundary_slice is not None:
                start_index, end_index = boundary_slice
                headers = _collapse_header_cells(header_row, start_index, end_index, schema)
                logical_start = _logical_column_start(header_row, start_index, schema)
                logical_width = len(headers)
                if start_index == 0 and _has_leading_stub_columns(headers, data_rows):
                    reflowed = _build_reflowed_table(table, headers, data_rows, _source_name)
                else:
                    sliced_data_rows = _slice_rows_by_logical_columns(data_rows, logical_start, logical_width)
                    reflowed = _build_reflowed_table(table, headers, sliced_data_rows, _source_name)
                    if reflowed is None:
                        reflowed = _build_reflowed_table(table, headers, data_rows, _source_name)
                    if reflowed is None and _source_name.endswith(":compact"):
                        reflowed = _build_header_only_reflowed_table(table, headers, _source_name)
                best_candidate = _pick_better_candidate(best_candidate, reflowed, schema)
                preserved_reflowed = _build_reflowed_table(table, headers, preserved_rows, f"{_source_name}:table_data")
                best_candidate = _pick_better_candidate(best_candidate, preserved_reflowed, schema)
        reflowed = _build_reflowed_table(table, header_row, data_rows, _source_name)
        if reflowed is None and _source_name.endswith(":compact"):
            reflowed = _build_header_only_reflowed_table(table, header_row, _source_name)
        best_candidate = _pick_better_candidate(best_candidate, reflowed, schema)
    return best_candidate


def match_table_schema(table: ExtractedTable, schemas: list[TableSchema]) -> TableMatchResult:
    best = TableMatchResult(schema_name=None, score=0.0, matched_columns=[])

    for schema in schemas:
        matched_columns, _required_hits = _matched_columns_for_row(table.headers, schema)
        weighted_score = _header_match_score(schema, table.headers)
        if weighted_score <= 0.0:
            continue

        if weighted_score > best.score:
            best = TableMatchResult(
                schema_name=schema.name,
                score=weighted_score,
                matched_columns=matched_columns,
            )

    return best


def rank_tables_by_schema(
    tables: list[ExtractedTable],
    schemas: list[TableSchema],
    segments: list[ExtractedSegment] | None = None,
) -> list[ExtractedTable]:
    ranked: list[ExtractedTable] = []
    for table in tables:
        if not table.import_headers:
            table.import_headers = list(table.headers)
        best_table = table
        best_match = match_table_schema(table, schemas)
        best_table.schema_debug_notes = [
            f"Initial headers: {table.headers}",
            f"Initial schema score: {best_match.score}",
        ]
        for schema in schemas:
            reflowed = reflow_table_to_schema(table, schema, segments)
            if reflowed is None:
                best_table.schema_debug_notes.append(f"{schema.name}: no reflow candidate found")
                continue
            match = match_table_schema(reflowed, [schema])
            reflowed.schema_debug_notes = list(best_table.schema_debug_notes) + [
                f"{schema.name}: candidate headers from {reflowed.header_source} -> {reflowed.headers}",
                f"{schema.name}: candidate score {match.score}",
            ]
            if match.score > best_match.score:
                best_table = reflowed
                best_match = match
            else:
                best_table.schema_debug_notes.append(
                    f"{schema.name}: candidate from {reflowed.header_source} scored {match.score} and was not selected"
                )
        best_table.matched_schema = best_match.schema_name
        best_table.schema_score = best_match.score
        if best_table.matched_schema is None:
            best_table.schema_debug_notes.append("No schema candidate beat the extracted headers.")
        ranked.append(best_table)
    merged_ranked = _merge_adjacent_tables(ranked, schemas)
    return sorted(merged_ranked, key=lambda item: (item.schema_score, item.confidence), reverse=True)
