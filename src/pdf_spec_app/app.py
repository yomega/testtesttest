from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .models import ExtractionOptions, ManualTableRegion, PagePreviewImage, SourceDocument, Specification, TableSchema
from .pipeline import ProcessingPipeline

TABLE_BACKEND_LABELS = {
    "pdfplumber": "pdfplumber",
    "Spire.PDF": "spire",
    "Microsoft Power Query Pdf.Tables()": "power_query",
}
TABLE_BACKEND_LABELS_BY_VALUE = {value: label for label, value in TABLE_BACKEND_LABELS.items()}
OCR_BACKEND_LABELS = {
    "Tesseract OCR Fallback": "tesseract",
    "Tesseract OCR Only": "tesseract_only",
    "Disabled": "disabled",
}
OCR_BACKEND_LABELS_BY_VALUE = {value: label for label, value in OCR_BACKEND_LABELS.items()}
WINDOW_STATE_PATH = Path.cwd() / ".runtime" / "window_state.json"
DEFAULT_SCHEMA_PANE_WIDTH = 320
PDFPLUMBER_STRATEGY_VALUES = ("lines", "lines_strict", "text")
DEFAULT_PDFPLUMBER_TOLERANCE_MAX = 1000


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__(useTk=False)
        self._load_tk_runtime()
        self.title("PDF Specification Builder")
        self.geometry("980x720")

        self.pipeline = ProcessingPipeline()
        self.selected_file: Path | None = None
        self.specification: Specification | None = None
        self.source_document: SourceDocument | None = None
        self.table_schemas: list[TableSchema] = default_table_schemas()
        self.extraction_options = ExtractionOptions()
        self.manual_table_regions: list[ManualTableRegion] = []
        self.progress_queue: Queue[tuple[str, object]] = Queue()
        self.is_generating = False
        self.schema_pane_width = DEFAULT_SCHEMA_PANE_WIDTH
        self.raw_import_whitespace_mode = tk.BooleanVar(value=False)
        self.ignore_tables_var = tk.BooleanVar(value=self.extraction_options.ignore_tables)
        self.pdfplumber_use_defaults_var = tk.BooleanVar(value=self.extraction_options.pdfplumber_use_default_table_settings)
        self.pdfplumber_vertical_strategy_var = tk.StringVar(value=self.extraction_options.pdfplumber_vertical_strategy)
        self.pdfplumber_horizontal_strategy_var = tk.StringVar(value=self.extraction_options.pdfplumber_horizontal_strategy)
        self.pdfplumber_text_x_tolerance_var = tk.IntVar(value=self.extraction_options.pdfplumber_text_x_tolerance)
        self.pdfplumber_text_y_tolerance_var = tk.IntVar(value=self.extraction_options.pdfplumber_text_y_tolerance)
        self.pdfplumber_debug_photoimages: list[ImageTk.PhotoImage] = []
        self.pdfplumber_page_photoimages: list[ImageTk.PhotoImage] = []
        self._pdfplumber_debug_refresh_after_id: str | None = None
        self.pdfplumber_text_x_max = DEFAULT_PDFPLUMBER_TOLERANCE_MAX
        self.pdfplumber_text_y_max = DEFAULT_PDFPLUMBER_TOLERANCE_MAX
        self.regenerate_needed_var = tk.StringVar(value="")

        self._build_layout()
        self._restore_window_state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_tk_runtime(self) -> None:
        tcl_library = os.environ.get("TCL_LIBRARY")
        tk_library = os.environ.get("TK_LIBRARY")

        if tcl_library:
            init_tcl = Path(tcl_library) / "init.tcl"
            if init_tcl.exists():
                self.tk.eval(f"source {{{init_tcl.as_posix()}}}")

        if tk_library:
            self.tk.eval(f"lappend auto_path {{{Path(tk_library).as_posix()}}}")

        self.loadtk()

    def _build_layout(self) -> None:
        shell = ttk.Frame(self, padding=16)
        shell.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(shell)
        controls.pack(fill=tk.X)

        self.import_button = ttk.Button(controls, text="Import File", command=self.import_file)
        self.import_button.pack(side=tk.LEFT, padx=(0, 8))
        self.region_button = ttk.Button(controls, text="Select Table Regions", command=self.select_table_regions)
        self.region_button.pack(side=tk.LEFT, padx=(0, 8))
        self.generate_button = ttk.Button(controls, text="Regenerate Spec", command=self.generate_spec)
        self.generate_button.pack(side=tk.LEFT, padx=(0, 8))
        self.export_button = ttk.Button(controls, text="Export DOCX", command=self.export_docx)
        self.export_button.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Select a source document to begin.")
        ttk.Label(shell, textvariable=self.status_var).pack(fill=tk.X, pady=(12, 8))
        self.regenerate_needed_label = ttk.Label(shell, textvariable=self.regenerate_needed_var, foreground="#a05a00")
        self.regenerate_needed_label.pack(fill=tk.X, pady=(0, 8))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            shell,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100.0,
            variable=self.progress_var,
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 8))

        self.panes = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        self.panes.pack(fill=tk.BOTH, expand=True)
        self.panes.bind("<ButtonRelease-1>", self._capture_schema_pane_width)
        self.bind("<Configure>", self._maintain_schema_pane_width)

        self.left_frame = ttk.Labelframe(self.panes, text="Table Schemas", padding=12, width=self.schema_pane_width)
        self.right_frame = ttk.Labelframe(self.panes, text="Specification Preview", padding=12)
        self.panes.add(self.left_frame, weight=0)
        self.panes.add(self.right_frame, weight=1)
        self.after(0, self._apply_schema_pane_width)

        settings_frame = ttk.Labelframe(self.left_frame, text="Extraction Settings", padding=12)
        settings_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(settings_frame, text="PDF backend").grid(row=0, column=0, sticky="w")
        ttk.Label(settings_frame, text="Spire.PDF / pdfplumber / Power Query SDK / OCR-only mode").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(8, 0),
        )

        ttk.Label(settings_frame, text="Extraction backend").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.table_backend_var = tk.StringVar(
            value=TABLE_BACKEND_LABELS_BY_VALUE.get(self.extraction_options.table_extraction_backend, "pdfplumber")
        )
        self.table_backend_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.table_backend_var,
            values=list(TABLE_BACKEND_LABELS.keys()),
            state="readonly",
            width=32,
        )
        self.table_backend_combo.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )
        self.table_backend_var.trace_add("write", self._on_table_backend_changed)
        self.table_backend_combo.bind("<<ComboboxSelected>>", self._on_table_backend_changed)

        self.pdfplumber_defaults_check = ttk.Checkbutton(
            settings_frame,
            text="pdfplumber defaults (no arguments)",
            variable=self.pdfplumber_use_defaults_var,
            command=self._on_pdfplumber_defaults_changed,
        )
        self.pdfplumber_defaults_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.pdfplumber_vertical_label = ttk.Label(settings_frame, text="pdfplumber vertical")
        self.pdfplumber_vertical_label.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.pdfplumber_vertical_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.pdfplumber_vertical_strategy_var,
            values=list(PDFPLUMBER_STRATEGY_VALUES),
            state="readonly",
            width=32,
        )
        self.pdfplumber_vertical_combo.grid(
            row=3,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )
        self.pdfplumber_vertical_strategy_var.trace_add("write", self._on_pdfplumber_defaults_changed)
        self.pdfplumber_vertical_combo.bind("<<ComboboxSelected>>", self._on_pdfplumber_defaults_changed)

        self.pdfplumber_text_x_label = ttk.Label(settings_frame, text="pdfplumber text_x_tolerance")
        self.pdfplumber_text_x_label.grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.pdfplumber_text_x_scale = tk.Scale(
            settings_frame,
            from_=1,
            to=self.pdfplumber_text_x_max,
            orient=tk.HORIZONTAL,
            variable=self.pdfplumber_text_x_tolerance_var,
            command=self._on_pdfplumber_tolerance_changed,
            showvalue=True,
        )
        self.pdfplumber_text_x_scale.grid(
            row=4,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )

        self.pdfplumber_horizontal_label = ttk.Label(settings_frame, text="pdfplumber horizontal")
        self.pdfplumber_horizontal_label.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.pdfplumber_horizontal_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.pdfplumber_horizontal_strategy_var,
            values=list(PDFPLUMBER_STRATEGY_VALUES),
            state="readonly",
            width=32,
        )
        self.pdfplumber_horizontal_combo.grid(
            row=5,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )
        self.pdfplumber_horizontal_strategy_var.trace_add("write", self._on_pdfplumber_defaults_changed)
        self.pdfplumber_horizontal_combo.bind("<<ComboboxSelected>>", self._on_pdfplumber_defaults_changed)

        self.pdfplumber_text_y_label = ttk.Label(settings_frame, text="pdfplumber text_y_tolerance")
        self.pdfplumber_text_y_label.grid(row=6, column=0, sticky="w", pady=(8, 0))
        self.pdfplumber_text_y_scale = tk.Scale(
            settings_frame,
            from_=1,
            to=self.pdfplumber_text_y_max,
            orient=tk.HORIZONTAL,
            variable=self.pdfplumber_text_y_tolerance_var,
            command=self._on_pdfplumber_tolerance_changed,
            showvalue=True,
        )
        self.pdfplumber_text_y_scale.grid(
            row=6,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )

        ttk.Label(settings_frame, text="OCR backend").grid(row=7, column=0, sticky="w", pady=(8, 0))
        self.ocr_backend_var = tk.StringVar(
            value=OCR_BACKEND_LABELS_BY_VALUE.get(self.extraction_options.ocr_backend, "Tesseract OCR Fallback")
        )
        self.ocr_backend_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.ocr_backend_var,
            values=list(OCR_BACKEND_LABELS.keys()),
            state="readonly",
            width=32,
        )
        self.ocr_backend_combo.grid(
            row=7,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )

        ttk.Label(settings_frame, text="OCR language").grid(row=8, column=0, sticky="w", pady=(8, 0))
        self.ocr_language_var = tk.StringVar(value=self.extraction_options.ocr_language)
        ttk.Entry(settings_frame, textvariable=self.ocr_language_var, width=32).grid(
            row=8,
            column=1,
            sticky="ew",
            padx=(8, 0),
            pady=(8, 0),
        )
        settings_frame.columnconfigure(1, weight=1)
        self._update_pdfplumber_slider_bounds()
        self._on_table_backend_changed()
        self.ocr_backend_var.trace_add("write", self._on_ocr_backend_changed)
        self.ocr_language_var.trace_add("write", self._on_ocr_language_changed)
        self._on_ocr_backend_changed()

        schema_controls = ttk.Frame(self.left_frame)
        schema_controls.pack(fill=tk.X, pady=(0, 8))

        self.ignore_tables_check = ttk.Checkbutton(
            schema_controls,
            text="Ignore Tables",
            variable=self.ignore_tables_var,
            command=self._on_ignore_tables_changed,
        )
        self.ignore_tables_check.pack(side=tk.LEFT, padx=(0, 8))
        self.schema_button = ttk.Button(schema_controls, text="Add Schema", command=self.add_table_schema)
        self.schema_button.pack(side=tk.LEFT, padx=(0, 8))
        self.edit_schema_button = ttk.Button(schema_controls, text="Edit Schema", command=self.edit_table_schema)
        self.edit_schema_button.pack(side=tk.LEFT, padx=(0, 8))
        self.remove_schema_button = ttk.Button(
            schema_controls,
            text="Remove Schema",
            command=self.remove_table_schema,
        )
        self.remove_schema_button.pack(side=tk.LEFT)

        self.schema_list = tk.Listbox(self.left_frame, height=12)
        self.schema_list.pack(fill=tk.BOTH, expand=True)
        self.schema_list.bind("<Double-Button-1>", self._on_schema_double_click)
        self._populate_schema_list()
        self._on_ignore_tables_changed()

        self.preview_notebook = ttk.Notebook(self.right_frame)
        self.preview_notebook.pack(fill=tk.BOTH, expand=True)

        spec_tab = ttk.Frame(self.preview_notebook)
        import_tab = ttk.Frame(self.preview_notebook)
        pdfplumber_pages_tab = ttk.Frame(self.preview_notebook)
        pdfplumber_debug_tab = ttk.Frame(self.preview_notebook)
        raw_tables_tab = ttk.Frame(self.preview_notebook)
        processed_tables_tab = ttk.Frame(self.preview_notebook)
        self.preview_notebook.add(spec_tab, text="Spec Preview")
        self.preview_notebook.add(import_tab, text="Raw Import Text")
        self.preview_notebook.add(pdfplumber_pages_tab, text="pdfplumber Pages")
        self.preview_notebook.add(pdfplumber_debug_tab, text="pdfplumber Tablefinder")
        self.preview_notebook.add(raw_tables_tab, text="Raw Tables Debug")
        self.preview_notebook.add(processed_tables_tab, text="Processed Tabled Debug")

        self.preview = tk.Text(spec_tab, wrap="word")
        self.preview.pack(fill=tk.BOTH, expand=True)

        import_controls = ttk.Frame(import_tab)
        import_controls.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(
            import_controls,
            text="Whitespace Mode",
            variable=self.raw_import_whitespace_mode,
            command=self._refresh_raw_import_view,
        ).pack(side=tk.LEFT)

        self.raw_import = tk.Text(import_tab, wrap="none")
        self.raw_import.pack(fill=tk.BOTH, expand=True)

        self.pdfplumber_page_canvas = tk.Canvas(pdfplumber_pages_tab, highlightthickness=0)
        self.pdfplumber_page_scrollbar = ttk.Scrollbar(
            pdfplumber_pages_tab,
            orient=tk.VERTICAL,
            command=self.pdfplumber_page_canvas.yview,
        )
        self.pdfplumber_page_canvas.configure(yscrollcommand=self.pdfplumber_page_scrollbar.set)
        self.pdfplumber_page_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pdfplumber_page_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.pdfplumber_page_container = ttk.Frame(self.pdfplumber_page_canvas)
        self.pdfplumber_page_canvas.create_window((0, 0), window=self.pdfplumber_page_container, anchor="nw")
        self.pdfplumber_page_container.bind(
            "<Configure>",
            lambda _event: self.pdfplumber_page_canvas.configure(
                scrollregion=self.pdfplumber_page_canvas.bbox("all")
            ),
        )
        self.pdfplumber_page_canvas.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
        self.pdfplumber_page_canvas.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
        self.pdfplumber_page_canvas.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)
        self.pdfplumber_page_scrollbar.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
        self.pdfplumber_page_scrollbar.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
        self.pdfplumber_page_scrollbar.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)
        self.pdfplumber_page_container.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
        self.pdfplumber_page_container.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
        self.pdfplumber_page_container.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)

        self.pdfplumber_debug_canvas = tk.Canvas(pdfplumber_debug_tab, highlightthickness=0)
        self.pdfplumber_debug_scrollbar = ttk.Scrollbar(
            pdfplumber_debug_tab,
            orient=tk.VERTICAL,
            command=self.pdfplumber_debug_canvas.yview,
        )
        self.pdfplumber_debug_canvas.configure(yscrollcommand=self.pdfplumber_debug_scrollbar.set)
        self.pdfplumber_debug_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pdfplumber_debug_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.pdfplumber_debug_container = ttk.Frame(self.pdfplumber_debug_canvas)
        self.pdfplumber_debug_canvas.create_window((0, 0), window=self.pdfplumber_debug_container, anchor="nw")
        self.pdfplumber_debug_container.bind(
            "<Configure>",
            lambda _event: self.pdfplumber_debug_canvas.configure(
                scrollregion=self.pdfplumber_debug_canvas.bbox("all")
            ),
        )
        self.pdfplumber_debug_canvas.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
        self.pdfplumber_debug_canvas.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
        self.pdfplumber_debug_canvas.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)
        self.pdfplumber_debug_scrollbar.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
        self.pdfplumber_debug_scrollbar.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
        self.pdfplumber_debug_scrollbar.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)
        self.pdfplumber_debug_container.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
        self.pdfplumber_debug_container.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
        self.pdfplumber_debug_container.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)

        self.raw_debug_tables = tk.Text(raw_tables_tab, wrap="word")
        self.raw_debug_tables.pack(fill=tk.BOTH, expand=True)

        self.debug_tables = tk.Text(processed_tables_tab, wrap="word")
        self.debug_tables.pack(fill=tk.BOTH, expand=True)

    def import_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select a technical document",
            filetypes=[
                ("Documents", "*.pdf *.txt *.md"),
                ("PDF", "*.pdf"),
                ("Text", "*.txt"),
                ("Markdown", "*.md"),
            ],
        )
        if not file_path:
            return

        self.selected_file = Path(file_path)
        self.manual_table_regions = []
        self._clear_regenerate_needed()
        self.status_var.set(f"Selected: {self.selected_file}. Generating specification...")
        self.generate_spec()

    def add_table_schema(self) -> None:
        dialog = TableSchemaDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.table_schemas.append(dialog.result)
        self._populate_schema_list()
        self.status_var.set(f"Loaded {len(self.table_schemas)} table schema(s).")

    def edit_table_schema(self) -> None:
        selected = self.schema_list.curselection()
        if not selected:
            messagebox.showwarning("No schema selected", "Select a table schema to edit.")
            return

        index = int(selected[0])
        dialog = TableSchemaDialog(self, schema=self.table_schemas[index], title="Edit Table Schema")
        self.wait_window(dialog)
        if dialog.result is None:
            return

        self.table_schemas[index] = dialog.result
        self._populate_schema_list()
        self.schema_list.selection_set(index)
        self.status_var.set(f"Updated schema: {dialog.result.name}")
        self._mark_regenerate_needed()

    def remove_table_schema(self) -> None:
        selected = self.schema_list.curselection()
        if not selected:
            messagebox.showwarning("No schema selected", "Select a table schema to remove.")
            return

        index = int(selected[0])
        schema = self.table_schemas[index]
        if not messagebox.askyesno("Remove schema", f"Remove schema '{schema.name}'?"):
            return

        del self.table_schemas[index]
        self._populate_schema_list()
        self.status_var.set(f"Removed schema: {schema.name}")
        self._mark_regenerate_needed()

    def select_table_regions(self) -> None:
        if self.ignore_tables_var.get():
            messagebox.showwarning("Tables ignored", "Turn off 'Ignore Tables' before selecting table regions.")
            return

        if self.selected_file is None or self.selected_file.suffix.lower() != ".pdf":
            messagebox.showwarning("PDF required", "Import a PDF document before selecting table regions.")
            return

        if self.source_document is None:
            messagebox.showwarning("No document loaded", "Import and generate a PDF first so page previews are available.")
            return

        if not self.source_document.page_preview_images:
            try:
                self.source_document.page_preview_images = self.pipeline.extractor.generate_pdf_page_previews(
                    self.selected_file
                )
            except Exception as exc:  # pragma: no cover - UI error handling
                messagebox.showerror("Preview generation failed", str(exc))
                return

        if not self.source_document.page_preview_images:
            messagebox.showwarning("No previews available", "The app could not render page previews for this PDF.")
            return

        dialog = TableRegionSelectorDialog(
            self,
            self.source_document.page_preview_images,
            self.manual_table_regions,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return

        self.manual_table_regions = dialog.result
        if self.table_backend_var.get().strip() != "pdfplumber":
            self.table_backend_var.set("pdfplumber")
        self.status_var.set(
            f"Saved {len(self.manual_table_regions)} manual table region(s). Regenerating specification..."
        )
        self._mark_regenerate_needed()
        if not self.is_generating:
            self.generate_spec()

    def _on_schema_double_click(self, _event: tk.Event) -> None:
        self.edit_table_schema()

    def _populate_schema_list(self) -> None:
        self.schema_list.delete(0, tk.END)
        for schema in self.table_schemas:
            self.schema_list.insert(tk.END, _format_schema_summary(schema))

    def generate_spec(self) -> None:
        if self.selected_file is None:
            messagebox.showwarning("Missing document", "Please import a file first.")
            return

        if self.is_generating:
            return

        self.is_generating = True
        self._set_controls_enabled(False)
        self.progress_var.set(0.0)
        self.status_var.set("Starting specification generation...")
        self.preview.delete("1.0", tk.END)
        self.raw_import.delete("1.0", tk.END)
        self._clear_pdfplumber_page_view()
        self._clear_pdfplumber_debug_view()
        self.raw_debug_tables.delete("1.0", tk.END)
        self.debug_tables.delete("1.0", tk.END)

        worker = threading.Thread(target=self._generate_spec_worker, daemon=True)
        worker.start()
        self.after(100, self._poll_progress_queue)

    def _generate_spec_worker(self) -> None:
        def on_progress(percent: float, message: str) -> None:
            self.progress_queue.put(("progress", (percent, message)))

        self._sync_extraction_options()
        try:
            specification = self.pipeline.process(
                self.selected_file,
                self.table_schemas,
                self.extraction_options,
                progress_callback=on_progress,
            )
        except Exception as exc:  # pragma: no cover - UI error handling
            self.progress_queue.put(("error", str(exc)))
            return

        self.progress_queue.put(("success", specification))

    def _poll_progress_queue(self) -> None:
        should_continue = self.is_generating

        try:
            while True:
                event_type, payload = self.progress_queue.get_nowait()
                if event_type == "progress":
                    percent, message = payload  # type: ignore[misc]
                    self.progress_var.set(float(percent))
                    self.status_var.set(str(message))
                elif event_type == "success":
                    self.specification = payload  # type: ignore[assignment]
                    self.source_document = self.pipeline.last_document
                    self._update_pdfplumber_slider_bounds(self.source_document)
                    self.preview.insert(tk.END, self._render_spec_preview(self.specification))
                    self._refresh_raw_import_view()
                    self._refresh_pdfplumber_page_view()
                    self._refresh_pdfplumber_debug_view()
                    self.raw_debug_tables.insert(tk.END, self._render_table_debug(self.source_document, processed=False))
                    self.debug_tables.insert(tk.END, self._render_table_debug(self.source_document, processed=True))
                    self.progress_var.set(100.0)
                    self.status_var.set("Specification generated. Review the preview, then export to DOCX.")
                    self._clear_regenerate_needed()
                    self.is_generating = False
                    self._set_controls_enabled(True)
                    should_continue = False
                elif event_type == "error":
                    self.progress_var.set(0.0)
                    self.status_var.set("Specification generation failed.")
                    self.is_generating = False
                    self._set_controls_enabled(True)
                    messagebox.showerror("Generation failed", str(payload))
                    should_continue = False
        except Empty:
            pass

        if should_continue:
            self.after(100, self._poll_progress_queue)

    def export_docx(self) -> None:
        if self.specification is None:
            messagebox.showwarning("Nothing to export", "Generate a specification first.")
            return

        destination = filedialog.asksaveasfilename(
            title="Export specification",
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
        )
        if not destination:
            return

        try:
            output = self.pipeline.export(self.specification, destination)
        except Exception as exc:  # pragma: no cover - UI error handling
            messagebox.showerror("Export failed", str(exc))
            return

        self.status_var.set(f"Exported: {output}")
        messagebox.showinfo("Export complete", f"Specification exported to:\n{output}")

    def _sync_extraction_options(self) -> None:
        ignore_tables = self.ignore_tables_var.get()
        self.extraction_options = ExtractionOptions(
            ignore_tables=ignore_tables,
            extract_tables=not ignore_tables,
            table_extraction_backend=TABLE_BACKEND_LABELS.get(self.table_backend_var.get().strip(), "pdfplumber"),
            pdfplumber_use_default_table_settings=self.pdfplumber_use_defaults_var.get(),
            pdfplumber_vertical_strategy=self.pdfplumber_vertical_strategy_var.get().strip() or "lines",
            pdfplumber_horizontal_strategy=self.pdfplumber_horizontal_strategy_var.get().strip() or "lines",
            pdfplumber_text_x_tolerance=self.pdfplumber_text_x_tolerance_var.get(),
            pdfplumber_text_y_tolerance=self.pdfplumber_text_y_tolerance_var.get(),
            ocr_backend=OCR_BACKEND_LABELS.get(self.ocr_backend_var.get().strip(), "tesseract"),
            ocr_language=self.ocr_language_var.get().strip() or "eng",
            manual_table_regions=list(self.manual_table_regions),
        )

    def _on_ignore_tables_changed(self) -> None:
        ignore_tables = self.ignore_tables_var.get()
        schema_state = tk.DISABLED if ignore_tables else tk.NORMAL

        self.schema_button.configure(state=schema_state)
        self.edit_schema_button.configure(state=schema_state)
        self.remove_schema_button.configure(state=schema_state)
        self.schema_list.configure(state=schema_state)
        self.region_button.configure(state=schema_state if not self.is_generating else tk.DISABLED)
        self.table_backend_combo.configure(state="readonly" if not self.is_generating else tk.DISABLED)
        self.ocr_backend_combo.configure(state="readonly" if not self.is_generating else tk.DISABLED)

        self.pdfplumber_defaults_check.configure(state=tk.NORMAL if not self.is_generating else tk.DISABLED)
        self.pdfplumber_vertical_combo.configure(state="readonly" if not self.is_generating else tk.DISABLED)
        self.pdfplumber_horizontal_combo.configure(state="readonly" if not self.is_generating else tk.DISABLED)
        self.pdfplumber_text_x_scale.configure(state=tk.NORMAL if not self.is_generating else tk.DISABLED)
        self.pdfplumber_text_y_scale.configure(state=tk.NORMAL if not self.is_generating else tk.DISABLED)
        self._on_table_backend_changed()
        self._on_pdfplumber_defaults_changed()
        self._mark_regenerate_needed()

    def _on_table_backend_changed(self, *_args) -> None:
        is_pdfplumber = TABLE_BACKEND_LABELS.get(self.table_backend_var.get().strip(), "pdfplumber") == "pdfplumber"
        widgets = (
            self.pdfplumber_defaults_check,
            self.pdfplumber_vertical_label,
            self.pdfplumber_vertical_combo,
            self.pdfplumber_text_x_label,
            self.pdfplumber_text_x_scale,
            self.pdfplumber_horizontal_label,
            self.pdfplumber_horizontal_combo,
            self.pdfplumber_text_y_label,
            self.pdfplumber_text_y_scale,
        )
        for widget in widgets:
            if is_pdfplumber:
                widget.grid()
            else:
                widget.grid_remove()
        self.after_idle(self._on_pdfplumber_defaults_changed)
        self._schedule_pdfplumber_debug_refresh()
        self._mark_regenerate_needed()

    def _on_pdfplumber_defaults_changed(self, *_args) -> None:
        use_defaults = self.pdfplumber_use_defaults_var.get()
        state = tk.DISABLED if use_defaults else "readonly"
        self.pdfplumber_vertical_combo.configure(state=state)
        self.pdfplumber_horizontal_combo.configure(state=state)
        vertical_text = self.pdfplumber_vertical_strategy_var.get().strip() == "text"
        horizontal_text = self.pdfplumber_horizontal_strategy_var.get().strip() == "text"
        is_pdfplumber = TABLE_BACKEND_LABELS.get(self.table_backend_var.get().strip(), "pdfplumber") == "pdfplumber"

        if not is_pdfplumber:
            self.pdfplumber_text_x_label.grid_remove()
            self.pdfplumber_text_x_scale.grid_remove()
            self.pdfplumber_text_y_label.grid_remove()
            self.pdfplumber_text_y_scale.grid_remove()
            self._schedule_pdfplumber_debug_refresh()
            return

        if use_defaults:
            self.pdfplumber_text_x_label.grid_remove()
            self.pdfplumber_text_x_scale.grid_remove()
            self.pdfplumber_text_y_label.grid_remove()
            self.pdfplumber_text_y_scale.grid_remove()
            self._schedule_pdfplumber_debug_refresh()
            return

        if vertical_text:
            self.pdfplumber_text_x_label.grid()
            self.pdfplumber_text_x_scale.grid()
        else:
            self.pdfplumber_text_x_label.grid_remove()
            self.pdfplumber_text_x_scale.grid_remove()

        if horizontal_text:
            self.pdfplumber_text_y_label.grid()
            self.pdfplumber_text_y_scale.grid()
        else:
            self.pdfplumber_text_y_label.grid_remove()
            self.pdfplumber_text_y_scale.grid_remove()

        self._schedule_pdfplumber_debug_refresh()
        self._mark_regenerate_needed()

    def _on_pdfplumber_tolerance_changed(self, _value: str) -> None:
        self._schedule_pdfplumber_debug_refresh()
        self._mark_regenerate_needed()

    def _on_ocr_backend_changed(self, *_args) -> None:
        ocr_backend = OCR_BACKEND_LABELS.get(self.ocr_backend_var.get().strip(), "tesseract")
        if self.ignore_tables_var.get():
            self.table_backend_combo.configure(state=tk.DISABLED)
            self.region_button.configure(state=tk.DISABLED)
        elif ocr_backend == "tesseract_only":
            self.table_backend_combo.configure(state=tk.DISABLED)
            self.region_button.configure(state=tk.DISABLED)
        else:
            self.table_backend_combo.configure(state="readonly")
            if not self.is_generating:
                self.region_button.configure(state=tk.NORMAL)
        self._mark_regenerate_needed()

    def _on_ocr_language_changed(self, *_args) -> None:
        self._mark_regenerate_needed()

    def _mark_regenerate_needed(self) -> None:
        if self.is_generating or (self.specification is None and self.source_document is None):
            return
        self.regenerate_needed_var.set("Regenerate needed to apply the latest option changes.")

    def _clear_regenerate_needed(self) -> None:
        self.regenerate_needed_var.set("")

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (
            self.import_button,
            self.ignore_tables_check,
            self.schema_button,
            self.edit_schema_button,
            self.remove_schema_button,
            self.region_button,
            self.generate_button,
            self.export_button,
        ):
            button.configure(state=state)
        if enabled:
            self._on_ignore_tables_changed()

    def _apply_schema_pane_width(self) -> None:
        self.update_idletasks()
        available_width = self.panes.winfo_width()
        if available_width <= self.schema_pane_width:
            self.after(50, self._apply_schema_pane_width)
            return
        self.left_frame.configure(width=self.schema_pane_width)
        self.left_frame.update_idletasks()
        try:
            self.panes.sashpos(0, self.schema_pane_width)
        except tk.TclError:
            self.after(50, self._apply_schema_pane_width)

    def _maintain_schema_pane_width(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self.after_idle(self._apply_schema_pane_width)

    def _capture_schema_pane_width(self, _event: tk.Event) -> None:
        try:
            self.schema_pane_width = self.panes.sashpos(0)
        except tk.TclError:
            return

    def _restore_window_state(self) -> None:
        if not WINDOW_STATE_PATH.exists():
            return
        try:
            state = json.loads(WINDOW_STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        geometry = state.get("geometry")
        window_state = state.get("state")
        pane_width = state.get("schema_pane_width")
        if isinstance(pane_width, int) and pane_width > 0:
            self.schema_pane_width = pane_width
        if geometry:
            self.geometry(str(geometry))
        if window_state in {"normal", "zoomed"}:
            self.after(0, lambda: self.state(window_state))
        self.after(0, self._apply_schema_pane_width)

    def _save_window_state(self) -> None:
        WINDOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "geometry": self.geometry(),
            "state": self.state(),
            "schema_pane_width": self.schema_pane_width,
        }
        WINDOW_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")

    def _on_close(self) -> None:
        try:
            self._save_window_state()
        except OSError:
            pass
        self.destroy()

    def _refresh_raw_import_view(self) -> None:
        self.raw_import.delete("1.0", tk.END)
        self.raw_import.insert(tk.END, self._render_raw_import_text(self.source_document, self.raw_import_whitespace_mode.get()))

    def _update_pdfplumber_slider_bounds(self, source_document: SourceDocument | None = None) -> None:
        width_limit = DEFAULT_PDFPLUMBER_TOLERANCE_MAX
        height_limit = DEFAULT_PDFPLUMBER_TOLERANCE_MAX

        if source_document is not None:
            debug = source_document.extraction_debug
            width_limit = self._parse_slider_bound(
                debug.get("pdfplumber_max_page_width_px"),
                DEFAULT_PDFPLUMBER_TOLERANCE_MAX,
            )
            height_limit = self._parse_slider_bound(
                debug.get("pdfplumber_max_page_height_px"),
                DEFAULT_PDFPLUMBER_TOLERANCE_MAX,
            )

        self.pdfplumber_text_x_max = width_limit
        self.pdfplumber_text_y_max = height_limit
        self.pdfplumber_text_x_scale.configure(to=width_limit)
        self.pdfplumber_text_y_scale.configure(to=height_limit)

        if self.pdfplumber_text_x_tolerance_var.get() > width_limit:
            self.pdfplumber_text_x_tolerance_var.set(width_limit)
        if self.pdfplumber_text_y_tolerance_var.get() > height_limit:
            self.pdfplumber_text_y_tolerance_var.set(height_limit)

    @staticmethod
    def _parse_slider_bound(raw_value: str | None, fallback: int) -> int:
        try:
            parsed = int(raw_value or "")
        except ValueError:
            return fallback
        return max(1, parsed)

    def _schedule_pdfplumber_debug_refresh(self) -> None:
        if self._pdfplumber_debug_refresh_after_id is not None:
            try:
                self.after_cancel(self._pdfplumber_debug_refresh_after_id)
            except tk.TclError:
                pass
            self._pdfplumber_debug_refresh_after_id = None
        self._pdfplumber_debug_refresh_after_id = self.after(200, self._refresh_pdfplumber_debug_images_from_controls)

    def _refresh_pdfplumber_debug_images_from_controls(self) -> None:
        self._pdfplumber_debug_refresh_after_id = None
        if self.is_generating or self.selected_file is None or self.source_document is None:
            return
        if self.selected_file.suffix.lower() != ".pdf":
            return

        self._sync_extraction_options()
        if self.extraction_options.table_extraction_backend != "pdfplumber":
            return

        try:
            debug_images = self.pipeline.extractor.generate_pdfplumber_debug_images(
                self.selected_file,
                self.extraction_options,
            )
        except Exception as exc:  # pragma: no cover - UI error handling
            self.status_var.set(f"pdfplumber tablefinder refresh failed: {exc}")
            return

        self.source_document.pdfplumber_debug_images = debug_images
        self.source_document.extraction_debug.update(
            {
                "pdf_backend": "pdfplumber",
                "extract_tables": str(self.extraction_options.extract_tables),
                "table_backend": self.extraction_options.table_extraction_backend,
                "ocr_backend": self.extraction_options.ocr_backend,
                "ocr_language": self.extraction_options.ocr_language,
                "pdfplumber_use_default_table_settings": str(
                    self.extraction_options.pdfplumber_use_default_table_settings
                ),
                "pdfplumber_vertical_strategy": self.extraction_options.pdfplumber_vertical_strategy,
                "pdfplumber_horizontal_strategy": self.extraction_options.pdfplumber_horizontal_strategy,
                "pdfplumber_text_x_tolerance": str(self.extraction_options.pdfplumber_text_x_tolerance),
                "pdfplumber_text_y_tolerance": str(self.extraction_options.pdfplumber_text_y_tolerance),
                "manual_table_regions": str(len(self.extraction_options.manual_table_regions)),
                "pdfplumber_table_settings": self.pipeline.extractor.describe_pdfplumber_table_settings(
                    self.extraction_options
                ),
            }
        )
        self._refresh_pdfplumber_debug_view()

    def _clear_pdfplumber_debug_view(self) -> None:
        for child in self.pdfplumber_debug_container.winfo_children():
            child.destroy()
        self.pdfplumber_debug_photoimages = []

    def _clear_pdfplumber_page_view(self) -> None:
        for child in self.pdfplumber_page_container.winfo_children():
            child.destroy()
        self.pdfplumber_page_photoimages = []

    def _on_pdfplumber_debug_mousewheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        step = -1 if delta > 0 else 1
        self.pdfplumber_debug_canvas.yview_scroll(step, "units")
        return "break"

    def _on_pdfplumber_page_mousewheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        step = -1 if delta > 0 else 1
        self.pdfplumber_page_canvas.yview_scroll(step, "units")
        return "break"

    def _on_pdfplumber_debug_mousewheel_linux(self, event: tk.Event) -> str:
        num = getattr(event, "num", 0)
        if num == 4:
            self.pdfplumber_debug_canvas.yview_scroll(-1, "units")
        elif num == 5:
            self.pdfplumber_debug_canvas.yview_scroll(1, "units")
        return "break"

    def _on_pdfplumber_page_mousewheel_linux(self, event: tk.Event) -> str:
        num = getattr(event, "num", 0)
        if num == 4:
            self.pdfplumber_page_canvas.yview_scroll(-1, "units")
        elif num == 5:
            self.pdfplumber_page_canvas.yview_scroll(1, "units")
        return "break"

    def _refresh_pdfplumber_page_view(self) -> None:
        self._clear_pdfplumber_page_view()
        if self.source_document is None:
            label = ttk.Label(
                self.pdfplumber_page_container,
                text="No pdfplumber page images are available for this document.",
            )
            label.pack(anchor="w", padx=8, pady=8)
            label.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
            label.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
            label.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)
            return

        if not self.source_document.page_preview_images and self.selected_file is not None and self.selected_file.suffix.lower() == ".pdf":
            try:
                self.source_document.page_preview_images = self.pipeline.extractor.generate_pdf_page_previews(
                    self.selected_file
                )
            except Exception:
                pass

        if not self.source_document.page_preview_images:
            label = ttk.Label(
                self.pdfplumber_page_container,
                text="No pdfplumber to_image page renders are available for this document.",
            )
            label.pack(anchor="w", padx=8, pady=8)
            label.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
            label.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
            label.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)
            return

        for preview in self.source_document.page_preview_images:
            page_label = ttk.Label(
                self.pdfplumber_page_container,
                text=f"Page {preview.page_number}",
            )
            page_label.pack(anchor="w", padx=8, pady=(8, 4))
            page_label.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
            page_label.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
            page_label.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)
            image = Image.open(BytesIO(preview.image_bytes))
            photo = ImageTk.PhotoImage(image)
            self.pdfplumber_page_photoimages.append(photo)
            image_label = ttk.Label(self.pdfplumber_page_container, image=photo)
            image_label.pack(anchor="w", padx=8, pady=(0, 12))
            image_label.bind("<MouseWheel>", self._on_pdfplumber_page_mousewheel)
            image_label.bind("<Button-4>", self._on_pdfplumber_page_mousewheel_linux)
            image_label.bind("<Button-5>", self._on_pdfplumber_page_mousewheel_linux)

    def _refresh_pdfplumber_debug_view(self) -> None:
        self._clear_pdfplumber_debug_view()
        if self.source_document is None or not self.source_document.pdfplumber_debug_images:
            label = ttk.Label(
                self.pdfplumber_debug_container,
                text="No pdfplumber debug_tablefinder images are available for this document.",
            )
            label.pack(anchor="w", padx=8, pady=8)
            label.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
            label.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
            label.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)
            return

        for page_number, image_bytes, image_label_text in self.source_document.pdfplumber_debug_images:
            page_label = ttk.Label(
                self.pdfplumber_debug_container,
                text=image_label_text,
            )
            page_label.pack(anchor="w", padx=8, pady=(8, 4))
            page_label.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
            page_label.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
            page_label.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)
            image = Image.open(BytesIO(image_bytes))
            image = self._overlay_manual_regions_on_debug_image(image, page_number)
            photo = ImageTk.PhotoImage(image)
            self.pdfplumber_debug_photoimages.append(photo)
            image_label = ttk.Label(self.pdfplumber_debug_container, image=photo)
            image_label.pack(anchor="w", padx=8, pady=(0, 12))
            image_label.bind("<MouseWheel>", self._on_pdfplumber_debug_mousewheel)
            image_label.bind("<Button-4>", self._on_pdfplumber_debug_mousewheel_linux)
            image_label.bind("<Button-5>", self._on_pdfplumber_debug_mousewheel_linux)

    def _overlay_manual_regions_on_debug_image(self, image: Image.Image, page_number: int) -> Image.Image:
        regions = [region for region in self.manual_table_regions if region.page_number == page_number]
        if not regions or self.source_document is None:
            return image
        # When manual regions exist, the tablefinder images are already generated
        # from the cropped regions themselves, so there is no full-page overlay to draw.
        return image

    @staticmethod
    def _render_spec_preview(specification: Specification) -> str:
        lines = [specification.title, f"Source: {specification.source_path}", ""]
        if specification.preview_warnings:
            lines.append("Evaluation Warnings")
            lines.append("-" * len("Evaluation Warnings"))
            for warning in specification.preview_warnings:
                lines.append(f"* {warning}")
            lines.append("")
        for section in specification.sections:
            lines.append(section.title)
            lines.append("-" * len(section.title))
            for statement in section.statements:
                suffix = "" if statement.status == "supported" else f" [{statement.status.upper()}]"
                lines.append(f"* {statement.text}{suffix}")
                for evidence in statement.evidence:
                    lines.append(evidence.to_formatted_string())
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _render_raw_import_text(source_document: SourceDocument | None, whitespace_mode: bool = False) -> str:
        if source_document is None:
            return "No raw import text is available yet."
        raw_text = source_document.raw_import_text or "[The extraction tool returned no raw import text.]"
        if not whitespace_mode:
            return raw_text
        return App._render_emacs_whitespace_mode(raw_text)

    @staticmethod
    def _render_emacs_whitespace_mode(text: str) -> str:
        rendered_lines: list[str] = []
        for line in text.splitlines():
            visible_line = line.replace("\t", "»").replace(" ", "·")
            rendered_lines.append(f"{visible_line}¶")
        if text.endswith("\n"):
            rendered_lines.append("¶")
        return "\n".join(rendered_lines) if rendered_lines else text.replace("\t", "»").replace(" ", "·")

    @staticmethod
    def _render_table_debug(source_document: SourceDocument | None, processed: bool) -> str:
        if source_document is None:
            return "No extraction debug data is available yet."

        tables = source_document.tables if processed else source_document.raw_tables
        heading = "Processed tables" if processed else "Raw extracted tables"

        lines = [
            source_document.title,
            f"Source: {source_document.path}",
            heading,
            f"Detected tables: {len(tables)}",
            "",
        ]

        extraction_debug = getattr(source_document, "extraction_debug", None)
        if processed and extraction_debug:
            lines.append("Backend settings")
            lines.append("-" * len("Backend settings"))
            for key, value in extraction_debug.items():
                lines.append(f"* {key}: {value}")
            lines.append("")

        if source_document.evaluation_warnings:
            lines.append("Evaluation Warnings")
            lines.append("-" * len("Evaluation Warnings"))
            for warning in source_document.evaluation_warnings:
                lines.append(f"* {warning}")
            lines.append("")

        if not tables:
            lines.append("No tables were extracted from this document.")
            return "\n".join(lines)

        for index, table in enumerate(tables, start=1):
            lines.append(f"Table {index}")
            lines.append(f"Page: {table.page_number}")
            lines.append(f"Confidence: {table.confidence:.2f}")
            lines.append(f"Backend: {getattr(table, 'backend', 'unknown')}")
            if processed and getattr(table, "extraction_box", None):
                lines.append(f"pdfplumber box: {table.extraction_box}")
            if processed and getattr(table, "extraction_debug_notes", None):
                lines.append("Extraction debug:")
                for note in table.extraction_debug_notes:
                    lines.append(f"  - {note}")
            if processed:
                lines.append(f"Header source: {getattr(table, 'header_source', 'table_extract')}")
                lines.append(f"Schema match: {table.matched_schema or 'None'}")
                lines.append(f"Schema score: {table.schema_score:.2f}")
            if processed and getattr(table, "schema_debug_notes", None):
                lines.append("Schema debug:")
                for note in table.schema_debug_notes:
                    lines.append(f"  - {note}")
            lines.append(f"Headers: {table.headers or ['Unknown']}")
            lines.append("Rows:")
            if table.rows:
                for row_number, row in enumerate(table.rows, start=1):
                    lines.append(f"  {row_number}. {row}")
            else:
                lines.append("  [No data rows extracted]")
            lines.append("Raw text:")
            lines.append(table.raw_text or "[No raw table text extracted]")
            lines.append("")

        return "\n".join(lines)


class TableRegionSelectorDialog(tk.Toplevel):
    AUTO_SCROLL_MARGIN_PX = 32
    AUTO_SCROLL_UNITS = 2

    def __init__(
        self,
        parent: App,
        page_previews: list[PagePreviewImage],
        regions: list[ManualTableRegion],
    ) -> None:
        super().__init__(parent)
        self.title("Select Table Regions")
        self.geometry("1200x860")
        self.minsize(900, 700)
        self.result: list[ManualTableRegion] | None = None
        self.page_previews = sorted(page_previews, key=lambda preview: preview.page_number)
        self.regions = [
            ManualTableRegion(
                page_number=region.page_number,
                left=region.left,
                top=region.top,
                right=region.right,
                bottom=region.bottom,
                label=region.label,
            )
            for region in regions
        ]
        self.current_page_index = 0
        self._photoimage: ImageTk.PhotoImage | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_rect_id: int | None = None
        self._page_region_indices: list[int] = []

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build_layout()
        self._render_current_page()

    def _build_layout(self) -> None:
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(shell)
        controls.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(controls, text="Previous Page", command=self._show_previous_page).pack(side=tk.LEFT)
        ttk.Button(controls, text="Next Page", command=self._show_next_page).pack(side=tk.LEFT, padx=(8, 0))
        self.page_label_var = tk.StringVar(value="Page 1")
        ttk.Label(controls, textvariable=self.page_label_var).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(controls, text="Delete Selected", command=self._delete_selected_region).pack(side=tk.RIGHT)
        ttk.Button(controls, text="Clear All", command=self._clear_all_regions).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(controls, text="Clear Page", command=self._clear_current_page).pack(side=tk.RIGHT, padx=(0, 8))

        content = ttk.Frame(shell)
        content.pack(fill=tk.BOTH, expand=True)

        sidebar = ttk.Labelframe(content, text="Page Regions", padding=8, width=260)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        sidebar.pack_propagate(False)

        ttk.Label(
            sidebar,
            text="Drag on the page to define a table crop.\nSelections are saved in page coordinates.",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))

        self.region_list = tk.Listbox(sidebar, height=18)
        self.region_list.pack(fill=tk.BOTH, expand=True)

        button_row = ttk.Frame(sidebar)
        button_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(button_row, text="Save", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(button_row, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        canvas_frame = ttk.Frame(content)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, background="#202020", highlightthickness=0)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

    def _current_preview(self) -> PagePreviewImage:
        return self.page_previews[self.current_page_index]

    def _show_previous_page(self) -> None:
        if self.current_page_index <= 0:
            return
        self.current_page_index -= 1
        self._render_current_page()

    def _show_next_page(self) -> None:
        if self.current_page_index >= len(self.page_previews) - 1:
            return
        self.current_page_index += 1
        self._render_current_page()

    def _render_current_page(self) -> None:
        preview = self._current_preview()
        image = Image.open(BytesIO(preview.image_bytes))
        self._photoimage = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photoimage)
        self.canvas.configure(scrollregion=(0, 0, image.width, image.height))
        self.page_label_var.set(f"Page {preview.page_number} of {len(self.page_previews)}")
        self._render_region_overlays()
        self._refresh_region_list()

    def _render_region_overlays(self) -> None:
        preview = self._current_preview()
        for index, region in enumerate(self._regions_for_current_page(), start=1):
            x0, y0, x1, y1 = self._region_to_canvas_box(region, preview)
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#00d27f", width=2)
            self.canvas.create_text(
                x0 + 6,
                max(8, y0 - 10),
                anchor="nw",
                fill="#00d27f",
                text=region.label or f"Region {index}",
            )

    def _regions_for_current_page(self) -> list[ManualTableRegion]:
        page_number = self._current_preview().page_number
        return [region for region in self.regions if region.page_number == page_number]

    def _refresh_region_list(self) -> None:
        self.region_list.delete(0, tk.END)
        page_number = self._current_preview().page_number
        self._page_region_indices = [index for index, region in enumerate(self.regions) if region.page_number == page_number]
        for index in self._page_region_indices:
            region = self.regions[index]
            self.region_list.insert(
                tk.END,
                region.label or f"Region {index + 1}: ({region.left:.1f}, {region.top:.1f}) -> ({region.right:.1f}, {region.bottom:.1f})",
            )

    def _on_canvas_press(self, event: tk.Event) -> None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        self._drag_start = (x, y)
        if self._drag_rect_id is not None:
            self.canvas.delete(self._drag_rect_id)
        self._drag_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="#ffb000", dash=(4, 2), width=2)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self._drag_start is None or self._drag_rect_id is None:
            return
        self._auto_scroll_canvas_for_drag(event.x, event.y)
        x0, y0 = self._drag_start
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self.canvas.coords(self._drag_rect_id, x0, y0, x1, y1)

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self._drag_start = None
        if self._drag_rect_id is not None:
            self.canvas.delete(self._drag_rect_id)
            self._drag_rect_id = None

        if abs(x1 - x0) < 8 or abs(y1 - y0) < 8:
            return

        preview = self._current_preview()
        left, top, right, bottom = self._canvas_box_to_region(x0, y0, x1, y1, preview)
        next_index = len(self._regions_for_current_page()) + 1
        self.regions.append(
            ManualTableRegion(
                page_number=preview.page_number,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                label=f"Page {preview.page_number} Region {next_index}",
            )
        )
        self._render_current_page()

    def _delete_selected_region(self) -> None:
        selection = self.region_list.curselection()
        if not selection:
            return
        region_index = self._page_region_indices[int(selection[0])]
        del self.regions[region_index]
        self._render_current_page()

    def _clear_current_page(self) -> None:
        page_number = self._current_preview().page_number
        self.regions = [region for region in self.regions if region.page_number != page_number]
        self._render_current_page()

    def _clear_all_regions(self) -> None:
        self.regions = []
        self._render_current_page()

    def _save(self) -> None:
        self.result = sorted(
            self.regions,
            key=lambda region: (region.page_number, region.top, region.left, region.bottom, region.right),
        )
        self.destroy()

    def _auto_scroll_canvas_for_drag(self, x: int, y: int) -> None:
        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        if x < self.AUTO_SCROLL_MARGIN_PX:
            self.canvas.xview_scroll(-self.AUTO_SCROLL_UNITS, "units")
        elif x > width - self.AUTO_SCROLL_MARGIN_PX:
            self.canvas.xview_scroll(self.AUTO_SCROLL_UNITS, "units")

        if y < self.AUTO_SCROLL_MARGIN_PX:
            self.canvas.yview_scroll(-self.AUTO_SCROLL_UNITS, "units")
        elif y > height - self.AUTO_SCROLL_MARGIN_PX:
            self.canvas.yview_scroll(self.AUTO_SCROLL_UNITS, "units")

    @staticmethod
    def _region_to_canvas_box(
        region: ManualTableRegion,
        preview: PagePreviewImage,
    ) -> tuple[float, float, float, float]:
        x_scale = preview.image_width_px / max(preview.page_width_pts, 1.0)
        y_scale = preview.image_height_px / max(preview.page_height_pts, 1.0)
        return (
            region.left * x_scale,
            region.top * y_scale,
            region.right * x_scale,
            region.bottom * y_scale,
        )

    @staticmethod
    def _canvas_box_to_region(
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        preview: PagePreviewImage,
    ) -> tuple[float, float, float, float]:
        x_scale = preview.page_width_pts / max(preview.image_width_px, 1)
        y_scale = preview.page_height_pts / max(preview.image_height_px, 1)
        left = max(0.0, min(x0, x1) * x_scale)
        top = max(0.0, min(y0, y1) * y_scale)
        right = min(preview.page_width_pts, max(x0, x1) * x_scale)
        bottom = min(preview.page_height_pts, max(y0, y1) * y_scale)
        return left, top, right, bottom


class TableSchemaDialog(tk.Toplevel):
    def __init__(self, parent: App, schema: TableSchema | None = None, title: str = "Add Table Schema") -> None:
        super().__init__(parent)
        self.title(title)
        self.result: TableSchema | None = None
        self.resizable(False, False)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Schema name").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Start header").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="End header").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Columns (optional, comma-separated)").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Required columns (optional, comma-separated)").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Weight").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            frame,
            text="Minimum: name + start header + end header",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.name_var = tk.StringVar(value=schema.name if schema else "")
        self.start_header_var = tk.StringVar(value=schema.start_header or "" if schema else "")
        self.end_header_var = tk.StringVar(value=schema.end_header or "" if schema else "")
        self.columns_var = tk.StringVar(value=", ".join(schema.columns) if schema else "")
        self.required_var = tk.StringVar(value=", ".join(schema.required_columns) if schema else "")
        self.weight_var = tk.StringVar(value=str(schema.weight) if schema else "1.5")

        ttk.Entry(frame, textvariable=self.name_var, width=42).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(frame, textvariable=self.start_header_var, width=42).grid(row=1, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(frame, textvariable=self.end_header_var, width=42).grid(row=2, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(frame, textvariable=self.columns_var, width=42).grid(row=3, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(frame, textvariable=self.required_var, width=42).grid(row=4, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(frame, textvariable=self.weight_var, width=42).grid(row=5, column=1, sticky="ew", padx=(8, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=7, column=0, columnspan=2, pady=(16, 0), sticky="e")
        ttk.Button(button_row, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(button_row, text="Save", command=self.save).pack(side=tk.RIGHT, padx=(0, 8))

    def save(self) -> None:
        name = self.name_var.get().strip()
        columns = [item.strip() for item in self.columns_var.get().split(",") if item.strip()]
        required = [item.strip() for item in self.required_var.get().split(",") if item.strip()]
        start_header = self.start_header_var.get().strip() or None
        end_header = self.end_header_var.get().strip() or None
        if not name or not start_header or not end_header:
            messagebox.showwarning(
                "Incomplete schema",
                "Name, start header, and end header are required.",
            )
            return

        try:
            weight = float(self.weight_var.get().strip())
        except ValueError:
            messagebox.showwarning("Invalid weight", "Weight must be a number.")
            return

        self.result = TableSchema(
            name=name,
            columns=columns,
            required_columns=required,
            start_header=start_header,
            end_header=end_header,
            weight=weight,
        )
        self.destroy()


def default_table_schemas() -> list[TableSchema]:
    return [
        TableSchema(
            name="partlist",
            columns=["description", "pattern no.", "v3"],
            required_columns=["description", "pattern no."],
            start_header="description",
            end_header="v3",
        )
    ]


def _format_schema_summary(schema: TableSchema) -> str:
    labels: list[str] = []
    if schema.columns:
        labels.append(", ".join(schema.columns))
    if schema.start_header and schema.end_header:
        labels.append(f"[{schema.start_header} -> {schema.end_header}]")
    return f"{schema.name}: {' '.join(labels).strip()}"


def main() -> int:
    app = App()
    app.mainloop()
    return 0
