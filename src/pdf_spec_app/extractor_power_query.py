from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

from .models import ExtractedTable
from .extractor_support import (
    POWER_QUERY_BOOTSTRAP_NAME,
    POWER_QUERY_RUNTIME_DIR,
    POWER_QUERY_TIMEOUT_SECONDS,
    ExtractionError,
    _decode_pqtest_text_output,
    _dedupe_preserve_order,
    _form_markdown_table,
    _normalize_power_query_table,
    _page_number_from_table_name,
    _sdk_extension_root,
    _tool_launch_env,
)


class PowerQueryBackendMixin:
    def _extract_power_query_tables(
        self,
        path: Path,
        evaluation_warnings: list[str],
        progress_callback=None,
    ) -> list[ExtractedTable]:
        pqtest_path = self._resolve_pqtest_path()
        extension_path = self._ensure_power_query_bootstrap_extension()
        runtime_dir = POWER_QUERY_RUNTIME_DIR / uuid.uuid4().hex
        runtime_dir.mkdir(parents=True, exist_ok=True)
        query_path = runtime_dir / "pdf_tables.query.pq"
        output_path = runtime_dir / "pdf_tables.query.pqout"
        try:
            self._report(progress_callback, 73.0, "Preparing Power Query SDK extraction...")
            query_path.write_text(self._build_power_query_formula(path), encoding="utf-8")

            self._report(progress_callback, 74.0, "Running PQTest.exe against Pdf.Tables()...")
            completed = subprocess.run(
                [str(pqtest_path), "run-compare", "-e", str(extension_path), "-q", str(query_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(pqtest_path.parent),
                env=_tool_launch_env(pqtest_path),
                timeout=POWER_QUERY_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or f"Exit code {completed.returncode}"
                raise ExtractionError(f"PQTest.exe failed while evaluating Pdf.Tables(). Details: {detail}")

            if not output_path.exists():
                raise ExtractionError("PQTest.exe completed but no .pqout file was generated for the Pdf.Tables() query.")

            self._report(progress_callback, 76.0, "Reading Power Query SDK output...")
            output_text = _decode_pqtest_text_output(output_path.read_text(encoding="utf-8"))
            records = json.loads(output_text or "[]")
            if not isinstance(records, list):
                raise ExtractionError("PQTest.exe returned an unexpected result shape for Pdf.Tables().")
            if not records:
                self._report(progress_callback, 77.0, "Power Query SDK completed but returned no table rows.")
                return []

            extracted_tables: list[ExtractedTable] = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                name = str(record.get("Name", "") or "")
                warnings_text = str(record.get("WarningText", "") or "")
                if warnings_text:
                    evaluation_warnings.extend(_dedupe_preserve_order(warnings_text.split(" || ")))

                headers_json = str(record.get("HeadersJson", "") or "[]")
                rows_json = str(record.get("RowsJson", "") or "[]")
                headers = [str(value).strip() for value in json.loads(headers_json)]
                data_rows = [
                    ["" if value is None else str(value).strip() for value in row]
                    for row in json.loads(rows_json)
                ]
                headers, data_rows = _normalize_power_query_table(headers, data_rows)
                raw_text = _form_markdown_table([headers, *data_rows])
                if not headers and not data_rows:
                    continue
                extracted_tables.append(
                    ExtractedTable(
                        page_number=_page_number_from_table_name(name),
                        headers=headers,
                        rows=data_rows,
                        import_headers=list(headers),
                        source_text=raw_text,
                        raw_text=raw_text,
                        confidence=0.93,
                        backend="power_query",
                    )
                )
            self._report(progress_callback, 77.0, f"Power Query returned {len(extracted_tables)} table candidate(s).")
            return extracted_tables
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(
                "PQTest.exe did not complete within 90 seconds while evaluating Pdf.Tables()."
            ) from exc
        except ExtractionError:
            raise
        except Exception as exc:  # pragma: no cover
            detail = str(exc).strip() or type(exc).__name__
            raise ExtractionError(
                "Microsoft Power Query Pdf.Tables() SDK extraction failed. "
                "This backend requires the Power Query SDK toolchain with PQTest.exe available locally. "
                f"Details: {detail}"
            ) from exc
        finally:
            for temp_file in runtime_dir.glob("*"):
                try:
                    temp_file.unlink()
                except OSError:
                    pass
            try:
                runtime_dir.rmdir()
            except OSError:
                pass

    @staticmethod
    def _build_power_query_formula(path: Path) -> str:
        escaped_path = str(path).replace('"', '""')
        return (
            "let\n"
            f'    Source = Pdf.Tables(File.Contents("{escaped_path}"), '
            '[Implementation="1.3", MultiPageTables=true, EnforceBorderLines=false]),\n'
            '    TablesOnly = Table.SelectRows(Source, each [Kind] = "Table"),\n'
            '    Indexed = Table.AddIndexColumn(TablesOnly, "TableIndex", 1, 1, Int64.Type),\n'
            '    HeadersJson = Table.AddColumn(Indexed, "HeadersJson", each Text.FromBinary(Json.FromValue(Table.ColumnNames([Data])), TextEncoding.Utf8), type text),\n'
            '    RowsJson = Table.AddColumn(HeadersJson, "RowsJson", each Text.FromBinary(Json.FromValue(Table.ToRows([Data])), TextEncoding.Utf8), type text),\n'
            '    WarningText = Table.AddColumn(RowsJson, "WarningText", each "", type text),\n'
            '    Output = Table.SelectColumns(WarningText, {"Name", "Kind", "TableIndex", "HeadersJson", "RowsJson", "WarningText"}),\n'
            '    JsonOutput = Text.FromBinary(Json.FromValue(Table.ToRecords(Output)), TextEncoding.Utf8)\n'
            "in\n"
            "    JsonOutput"
        )

    @staticmethod
    def _resolve_pqtest_path() -> Path:
        candidates: list[Path] = []
        env_path = os.environ.get("PQTEST_PATH", "").strip()
        if env_path:
            env_candidate = Path(env_path)
            candidates.append(env_candidate / "PQTest.exe" if env_candidate.is_dir() else env_candidate)

        vscode_extensions = _sdk_extension_root()
        if vscode_extensions.exists():
            sdk_roots = sorted(
                [path for path in vscode_extensions.glob("powerquery.vscode-powerquery-sdk-*") if path.is_dir()],
                reverse=True,
            )
            for root in sdk_roots:
                preferred = root / "PQTest.exe"
                packaged = [candidate for candidate in root.rglob("PQTest.exe") if candidate != preferred]
                if preferred.exists():
                    candidates.append(preferred)
                candidates.extend(sorted(packaged))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise ExtractionError("PQTest.exe was not found in the default Power Query SDK extension location.")

    def _resolve_makepqx_path(self) -> Path:
        candidates: list[Path] = []
        env_path = os.environ.get("MAKEPQX_PATH", "").strip()
        if env_path:
            env_candidate = Path(env_path)
            candidates.append(env_candidate / "MakePQX.exe" if env_candidate.is_dir() else env_candidate)

        vscode_extensions = _sdk_extension_root()
        if vscode_extensions.exists():
            sdk_roots = sorted(
                [path for path in vscode_extensions.glob("powerquery.vscode-powerquery-sdk-*") if path.is_dir()],
                reverse=True,
            )
            for root in sdk_roots:
                preferred = root / "MakePQX.exe"
                packaged = [candidate for candidate in root.rglob("MakePQX.exe") if candidate != preferred]
                if preferred.exists():
                    candidates.append(preferred)
                candidates.extend(sorted(packaged))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise ExtractionError("MakePQX.exe was not found in the default Power Query SDK extension location.")

    def _ensure_power_query_bootstrap_extension(self) -> Path:
        makepqx_path = self._resolve_makepqx_path()
        template_root = self._resolve_power_query_template_root()
        source_dir = POWER_QUERY_RUNTIME_DIR / "bootstrap_source"
        output_dir = POWER_QUERY_RUNTIME_DIR / "bootstrap_build"
        extension_path = output_dir / f"{POWER_QUERY_BOOTSTRAP_NAME}.mez"

        if extension_path.exists():
            return extension_path

        source_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_power_query_bootstrap_source(source_dir, template_root)

        completed = subprocess.run(
            [str(makepqx_path), "compile", str(source_dir), "-d", str(output_dir), "-t", POWER_QUERY_BOOTSTRAP_NAME],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(makepqx_path.parent),
            env=_tool_launch_env(makepqx_path),
            timeout=POWER_QUERY_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0 or not extension_path.exists():
            detail = completed.stderr.strip() or completed.stdout.strip() or f"Exit code {completed.returncode}"
            raise ExtractionError(f"MakePQX.exe failed while building the bootstrap connector. Details: {detail}")

        return extension_path

    def _resolve_power_query_template_root(self) -> Path:
        sdk_roots = sorted(
            [path for path in _sdk_extension_root().glob("powerquery.vscode-powerquery-sdk-*") if path.is_dir()],
            reverse=True,
        )
        for root in sdk_roots:
            template_root = root / "templates"
            if template_root.exists():
                return template_root
        raise ExtractionError("Power Query SDK templates were not found in the default extension location.")

    def _write_power_query_bootstrap_source(self, source_dir: Path, template_root: Path) -> None:
        pq_template = (template_root / "PQConn.pq").read_text(encoding="utf-8")
        proj_template = (template_root / "PQConn.proj").read_text(encoding="utf-8")
        resx_template = (template_root / "resources.resx").read_text(encoding="utf-8")

        replacements = {
            "{{ProjectName}}": POWER_QUERY_BOOTSTRAP_NAME,
        }
        for filename, template_text in (
            (f"{POWER_QUERY_BOOTSTRAP_NAME}.pq", pq_template),
            (f"{POWER_QUERY_BOOTSTRAP_NAME}.proj", proj_template),
            ("resources.resx", resx_template),
        ):
            rendered = template_text
            for key, value in replacements.items():
                rendered = rendered.replace(key, value)
            (source_dir / filename).write_text(rendered, encoding="utf-8")

        for size in ("16", "20", "24", "32", "40", "48", "64", "80"):
            source_icon = template_root / f"PQConn{size}.png"
            target_icon = source_dir / f"{POWER_QUERY_BOOTSTRAP_NAME}{size}.png"
            if not target_icon.exists():
                target_icon.write_bytes(source_icon.read_bytes())
