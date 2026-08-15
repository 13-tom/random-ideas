"""Cut / remove silence / reframe / caption — wraps run_pipeline.py."""
import csv
import sys
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

import theme
from widgets import CaptionOptionsPanel, card, checkbox, entry, field_row, ghost_button, option_menu

ASPECT_CHOICES = ["original", "vertical", "square", "portrait", "landscape"]
TRACK_MODE_CHOICES = ["dynamic", "static", "fanpage"]


class PipelinePage(ctk.CTkFrame):
    title = "Cut & Process"
    run_label = "Run pipeline"
    blurb = "Cut clips from raw footage by timestamp, trim silence, crop for Reels, and caption — all in one pass."

    def __init__(self, parent, repo_dir: Path):
        super().__init__(parent, fg_color="transparent")
        self.repo_dir = repo_dir
        self.script_path = repo_dir / "run_pipeline.py"

        self.video_path = ctk.StringVar()
        self.csv_path = ctk.StringVar()
        self.output_dir = ctk.StringVar(value=str(Path.cwd() / "pipeline_output"))
        self.reencode = ctk.BooleanVar(value=False)
        self.no_gpu = ctk.BooleanVar(value=False)
        self.remove_silence = ctk.BooleanVar(value=False)
        self.min_silence = ctk.StringVar(value="0.7")
        self.padding = ctk.StringVar(value="0.12")
        self.noise_db = ctk.StringVar(value="-35dB")
        self.aspect = ctk.StringVar(value="original")
        self.track_faces = ctk.BooleanVar(value=False)
        self.track_mode = ctk.StringVar(value="dynamic")

        self._build()

    def _build(self):
        body = card(self, "1 · Source video")
        row = field_row(body, "Video file")
        entry(row, textvariable=self.video_path, placeholder="Pick your raw .mp4").pack(side="left", fill="x", expand=True)
        ghost_button(row, "Browse", self._pick_video).pack(side="left", padx=(10, 0))

        body = card(self, "2 · Which parts to cut",
                    "Load a CSV (start,end,label per row) or build the clip list below. "
                    "Times accept HH:MM:SS, MM:SS, or plain seconds.")
        row = field_row(body, "Timestamps CSV")
        entry(row, textvariable=self.csv_path, placeholder="optional if you add clips below").pack(side="left", fill="x", expand=True)
        ghost_button(row, "Load CSV", self._pick_csv).pack(side="left", padx=(10, 0))

        add_row = ctk.CTkFrame(body, fg_color="transparent")
        add_row.pack(fill="x", pady=(10, 6))
        self.new_start = entry(add_row, placeholder="start e.g. 0:05", width=140)
        self.new_start.pack(side="left")
        self.new_end = entry(add_row, placeholder="end e.g. 0:12", width=140)
        self.new_end.pack(side="left", padx=8)
        self.new_label = entry(add_row, placeholder="label (optional)", width=180)
        self.new_label.pack(side="left")
        ghost_button(add_row, "+ Add clip", self._add_clip_row, width=100).pack(side="left", padx=8)
        ghost_button(add_row, "Remove selected", self._remove_clip_row, width=130).pack(side="left")

        table_frame = ctk.CTkFrame(body, fg_color="transparent")
        table_frame.pack(fill="x", pady=(4, 0))
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Clip.Treeview", background=theme.SURFACE_ALT, fieldbackground=theme.SURFACE_ALT,
                         foreground=theme.TEXT, rowheight=26, borderwidth=0)
        style.map("Clip.Treeview", background=[("selected", theme.ACCENT_SOFT)])
        style.configure("Clip.Treeview.Heading", background=theme.SURFACE, foreground=theme.TEXT_MUTED, borderwidth=0)
        self.clip_table = ttk.Treeview(table_frame, columns=("start", "end", "label"), show="headings",
                                        height=5, style="Clip.Treeview")
        for col, text, w in (("start", "Start", 120), ("end", "End", 120), ("label", "Label", 220)):
            self.clip_table.heading(col, text=text)
            self.clip_table.column(col, width=w, anchor="w")
        self.clip_table.pack(fill="x")

        body = card(self, "3 · Output folder")
        row = field_row(body, "Save results to")
        entry(row, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ghost_button(row, "Browse", self._pick_output_dir).pack(side="left", padx=(10, 0))

        body = card(self, "4 · Processing options")
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=4)
        checkbox(row1, "Frame-accurate cuts (--reencode)", self.reencode).pack(side="left")
        checkbox(row1, "Force CPU (--no-gpu)", self.no_gpu).pack(side="left", padx=20)

        ctk.CTkLabel(body, text="Remove silence", font=theme.font(13, "bold"), text_color=theme.TEXT).pack(
            anchor="w", pady=(14, 4))
        checkbox(body, "Jump-cut out silent gaps (Descript/CapCut style)", self.remove_silence).pack(anchor="w")
        sil_opts = ctk.CTkFrame(body, fg_color="transparent")
        sil_opts.pack(fill="x", padx=24, pady=(6, 0))
        for i, (label, var, w) in enumerate([("Min silence (s)", self.min_silence, 70),
                                              ("Padding (s)", self.padding, 70),
                                              ("Noise floor", self.noise_db, 70)]):
            ctk.CTkLabel(sil_opts, text=label, text_color=theme.TEXT_MUTED, font=theme.font(12)).grid(
                row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 18, 6))
            entry(sil_opts, textvariable=var, width=w).grid(row=0, column=i * 2 + 1)

        ctk.CTkLabel(body, text="Crop for Reels / Shorts", font=theme.font(13, "bold"), text_color=theme.TEXT).pack(
            anchor="w", pady=(16, 4))
        aspect_row = ctk.CTkFrame(body, fg_color="transparent")
        aspect_row.pack(fill="x")
        option_menu(aspect_row, ASPECT_CHOICES, self.aspect, width=120).pack(side="left")
        checkbox(aspect_row, "Smart face tracking", self.track_faces).pack(side="left", padx=(18, 8))
        option_menu(aspect_row, TRACK_MODE_CHOICES, self.track_mode, width=110).pack(side="left")

        ctk.CTkLabel(body, text="Captions (always generated — free, local, once-per-machine model download)",
                     font=theme.font(13, "bold"), text_color=theme.TEXT).pack(anchor="w", pady=(16, 6))
        self.caption_panel = CaptionOptionsPanel(body, style_choices=["plain", "word", "highlight"],
                                                  default_style="plain", default_position="bottom")
        self.caption_panel.pack(fill="x")

    # -- pickers ---------------------------------------------------------
    def _pick_video(self):
        path = filedialog.askopenfilename(title="Choose source video",
                                           filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")])
        if path:
            self.video_path.set(path)

    def _pick_csv(self):
        path = filedialog.askopenfilename(title="Choose timestamps CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.csv_path.set(path)
            self._load_csv_into_table(path)

    def _pick_output_dir(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_dir.set(path)

    def _load_csv_into_table(self, path):
        self.clip_table.delete(*self.clip_table.get_children())
        with open(path, newline="") as f:
            for row in csv.reader(f):
                if not row:
                    continue
                start, end = row[0], row[1] if len(row) > 1 else ""
                label = row[2] if len(row) > 2 else ""
                self.clip_table.insert("", "end", values=(start, end, label))

    def _add_clip_row(self):
        start = self.new_start.get().strip()
        end = self.new_end.get().strip()
        label = self.new_label.get().strip()
        if not start or not end:
            messagebox.showwarning("Missing values", "Enter both a start and end time.")
            return
        self.clip_table.insert("", "end", values=(start, end, label))
        self.new_start.delete(0, "end")
        self.new_end.delete(0, "end")
        self.new_label.delete(0, "end")

    def _remove_clip_row(self):
        for item in self.clip_table.selection():
            self.clip_table.delete(item)

    def _write_table_to_csv(self) -> Path:
        out_path = Path(self.output_dir.get())
        out_path.mkdir(parents=True, exist_ok=True)
        csv_path = out_path / "timestamps_from_gui.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            for item in self.clip_table.get_children():
                writer.writerow(self.clip_table.item(item, "values"))
        return csv_path

    def _resolve_csv_path(self):
        if self.clip_table.get_children():
            return self._write_table_to_csv()
        if self.csv_path.get().strip():
            return Path(self.csv_path.get().strip())
        return None

    # -- command building --------------------------------------------------
    def build_command(self):
        video = self.video_path.get().strip()
        if not video:
            messagebox.showerror("Missing video", "Pick a source video file first.")
            return None
        if not Path(video).exists():
            messagebox.showerror("Video not found", f"Can't find:\n{video}")
            return None

        csv_path = self._resolve_csv_path()
        if csv_path is None:
            messagebox.showerror("Missing timestamps", "Load a CSV or add at least one clip row.")
            return None

        cmd = [sys.executable, str(self.script_path), video, str(csv_path), "-o", self.output_dir.get().strip()]
        if self.reencode.get():
            cmd.append("--reencode")
        if self.no_gpu.get():
            cmd.append("--no-gpu")
        if self.remove_silence.get():
            cmd.append("--remove-silence")
            cmd += ["--min-silence", self.min_silence.get() or "0.7"]
            cmd += ["--padding", self.padding.get() or "0.12"]
            cmd += ["--noise-db", self.noise_db.get() or "-35dB"]
        if self.aspect.get() != "original":
            cmd += ["--aspect", self.aspect.get()]
            if self.track_faces.get():
                cmd.append("--track-faces")
                cmd += ["--track-mode", self.track_mode.get()]
        cmd += self.caption_panel.as_args()
        return cmd
