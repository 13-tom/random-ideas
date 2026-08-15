#!/usr/bin/env python3
"""Desktop GUI for the FFmpeg Bulk Cutter pipeline.

Wraps run_pipeline.py (cut -> remove silence -> reframe -> caption) behind
a point-and-click interface, so you don't need to touch a terminal or write
a CSV by hand.

Run it with:
    python gui/app.py
(see ../run_gui.sh / ../run_gui.bat for a one-click launcher)
"""
from __future__ import annotations

import csv
import queue
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

REPO_DIR = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT = REPO_DIR / "run_pipeline.py"

ASPECT_CHOICES = ["original", "vertical", "square", "portrait", "landscape"]
TRACK_MODE_CHOICES = ["dynamic", "static", "fanpage"]
LANGUAGE_CHOICES = ["auto", "en", "hi", "hinglish"]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
CAPTION_STYLE_CHOICES = ["plain", "word", "highlight"]
POSITION_CHOICES = ["bottom", "middle", "top"]

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def section(parent, title):
    frame = ctk.CTkFrame(parent, corner_radius=12)
    frame.pack(fill="x", padx=16, pady=(0, 14))
    label = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=15, weight="bold"))
    label.pack(anchor="w", padx=16, pady=(14, 6))
    body = ctk.CTkFrame(frame, fg_color="transparent")
    body.pack(fill="x", padx=16, pady=(0, 16))
    return body


def labeled_row(parent, label_text, widget_factory, width=None):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=4)
    label = ctk.CTkLabel(row, text=label_text, width=150, anchor="w")
    label.pack(side="left")
    widget = widget_factory(row)
    widget.pack(side="left", fill="x", expand=True, padx=(8, 0))
    return widget


class ClipperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Clipper Studio — FFmpeg Bulk Cutter")
        self.geometry("980x860")
        self.minsize(860, 640)

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

        self.language = ctk.StringVar(value="auto")
        self.model = ctk.StringVar(value="small")
        self.caption_style = ctk.StringVar(value="plain")
        self.text_color = ctk.StringVar(value="white")
        self.highlight_color = ctk.StringVar(value="yellow")
        self.position = ctk.StringVar(value="bottom")
        self.all_caps = ctk.BooleanVar(value=False)
        self.box_highlight = ctk.BooleanVar(value=False)

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_layout()
        self.after(100, self._poll_log_queue)

    # ------------------------------------------------------------------ UI

    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(
            header, text="Clipper Studio", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Cut clips from raw footage, crop for Reels, and caption them — no terminal required.",
            text_color="gray70",
        ).pack(anchor="w")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._build_source_section(scroll)
        self._build_timestamps_section(scroll)
        self._build_output_section(scroll)
        self._build_options_section(scroll)

        self._build_run_bar()
        self._build_log_panel()

    def _build_source_section(self, parent):
        body = section(parent, "1. Source video")

        def video_entry(row):
            return ctk.CTkEntry(row, textvariable=self.video_path, placeholder_text="Pick your raw .mp4 file")

        entry = labeled_row(body, "Video file", video_entry)
        ctk.CTkButton(entry.master, text="Browse", width=90, command=self._pick_video).pack(side="left", padx=(8, 0))

    def _build_timestamps_section(self, parent):
        body = section(parent, "2. Which parts to cut")

        mode_row = ctk.CTkFrame(body, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(mode_row, text="Timestamps CSV", width=150, anchor="w").pack(side="left")
        csv_entry = ctk.CTkEntry(mode_row, textvariable=self.csv_path, placeholder_text="start,end,label per row")
        csv_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ctk.CTkButton(mode_row, text="Load CSV", width=90, command=self._pick_csv).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            body,
            text="...or build the clip list here (times as HH:MM:SS, MM:SS, or seconds):",
            text_color="gray70",
        ).pack(anchor="w", pady=(8, 4))

        add_row = ctk.CTkFrame(body, fg_color="transparent")
        add_row.pack(fill="x", pady=4)
        self.new_start = ctk.CTkEntry(add_row, placeholder_text="start e.g. 0:05", width=140)
        self.new_start.pack(side="left")
        self.new_end = ctk.CTkEntry(add_row, placeholder_text="end e.g. 0:12", width=140)
        self.new_end.pack(side="left", padx=8)
        self.new_label = ctk.CTkEntry(add_row, placeholder_text="label (optional)", width=180)
        self.new_label.pack(side="left")
        ctk.CTkButton(add_row, text="+ Add clip", width=100, command=self._add_clip_row).pack(side="left", padx=8)
        ctk.CTkButton(add_row, text="Remove selected", width=130, command=self._remove_clip_row).pack(side="left")

        table_frame = ctk.CTkFrame(body, fg_color="transparent")
        table_frame.pack(fill="x", pady=(6, 0))
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Clip.Treeview", background="#2b2b2b", fieldbackground="#2b2b2b",
                         foreground="white", rowheight=26, borderwidth=0)
        style.configure("Clip.Treeview.Heading", background="#1f1f1f", foreground="white")
        self.clip_table = ttk.Treeview(
            table_frame, columns=("start", "end", "label"), show="headings",
            height=6, style="Clip.Treeview",
        )
        for col, text, w in (("start", "Start", 120), ("end", "End", 120), ("label", "Label", 220)):
            self.clip_table.heading(col, text=text)
            self.clip_table.column(col, width=w, anchor="w")
        self.clip_table.pack(fill="x")

    def _build_output_section(self, parent):
        body = section(parent, "3. Output folder")

        def out_entry(row):
            return ctk.CTkEntry(row, textvariable=self.output_dir)

        row = labeled_row(body, "Save results to", out_entry)
        ctk.CTkButton(row.master, text="Browse", width=90, command=self._pick_output_dir).pack(side="left", padx=(8, 0))

    def _build_options_section(self, parent):
        body = section(parent, "4. Processing options")

        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=4)
        ctk.CTkCheckBox(row1, text="Frame-accurate cuts (--reencode)", variable=self.reencode).pack(side="left")
        ctk.CTkCheckBox(row1, text="Force CPU (--no-gpu)", variable=self.no_gpu).pack(side="left", padx=20)

        # Remove silence
        sil_row = ctk.CTkFrame(body, fg_color="transparent")
        sil_row.pack(fill="x", pady=(12, 4))
        ctk.CTkCheckBox(sil_row, text="Remove silence (jump-cut style)", variable=self.remove_silence).pack(side="left")
        sil_opts = ctk.CTkFrame(body, fg_color="transparent")
        sil_opts.pack(fill="x", pady=(0, 4), padx=20)
        ctk.CTkLabel(sil_opts, text="Min silence (s)").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(sil_opts, textvariable=self.min_silence, width=80).grid(row=0, column=1, padx=(6, 20))
        ctk.CTkLabel(sil_opts, text="Padding (s)").grid(row=0, column=2, sticky="w")
        ctk.CTkEntry(sil_opts, textvariable=self.padding, width=80).grid(row=0, column=3, padx=(6, 20))
        ctk.CTkLabel(sil_opts, text="Noise floor").grid(row=0, column=4, sticky="w")
        ctk.CTkEntry(sil_opts, textvariable=self.noise_db, width=80).grid(row=0, column=5, padx=(6, 0))

        # Aspect / reframe
        aspect_row = ctk.CTkFrame(body, fg_color="transparent")
        aspect_row.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(aspect_row, text="Crop to aspect ratio", width=150, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(aspect_row, values=ASPECT_CHOICES, variable=self.aspect).pack(side="left")
        ctk.CTkCheckBox(aspect_row, text="Smart face tracking", variable=self.track_faces).pack(side="left", padx=20)
        ctk.CTkOptionMenu(aspect_row, values=TRACK_MODE_CHOICES, variable=self.track_mode, width=110).pack(side="left")

        # Captions (the pipeline always transcribes + burns captions; these
        # options control the style, not whether captioning happens)
        cap_row = ctk.CTkFrame(body, fg_color="transparent")
        cap_row.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(
            cap_row,
            text="Captions (always generated — free, local, runs on first use)",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left")

        cap_opts = ctk.CTkFrame(body, fg_color="transparent")
        cap_opts.pack(fill="x", pady=(0, 4), padx=20)
        ctk.CTkLabel(cap_opts, text="Language").grid(row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(cap_opts, values=LANGUAGE_CHOICES, variable=self.language, width=110).grid(row=0, column=1, padx=(6, 20))
        ctk.CTkLabel(cap_opts, text="Whisper model").grid(row=0, column=2, sticky="w")
        ctk.CTkOptionMenu(cap_opts, values=MODEL_CHOICES, variable=self.model, width=110).grid(row=0, column=3, padx=(6, 20))
        ctk.CTkLabel(cap_opts, text="Caption style").grid(row=0, column=4, sticky="w")
        ctk.CTkOptionMenu(cap_opts, values=CAPTION_STYLE_CHOICES, variable=self.caption_style, width=110).grid(row=0, column=5, padx=(6, 0))

        ctk.CTkLabel(cap_opts, text="Position").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ctk.CTkOptionMenu(cap_opts, values=POSITION_CHOICES, variable=self.position, width=110).grid(row=1, column=1, padx=(6, 20), pady=(8, 0))
        ctk.CTkLabel(cap_opts, text="Text color").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ctk.CTkEntry(cap_opts, textvariable=self.text_color, width=110).grid(row=1, column=3, padx=(6, 20), pady=(8, 0))
        ctk.CTkLabel(cap_opts, text="Highlight color").grid(row=1, column=4, sticky="w", pady=(8, 0))
        ctk.CTkEntry(cap_opts, textvariable=self.highlight_color, width=110).grid(row=1, column=5, pady=(8, 0))

        ctk.CTkCheckBox(cap_opts, text="ALL CAPS", variable=self.all_caps).grid(row=2, column=0, pady=(8, 0), sticky="w")
        ctk.CTkCheckBox(cap_opts, text="Highlight box (Opus Clip style)", variable=self.box_highlight).grid(row=2, column=1, columnspan=2, pady=(8, 0), sticky="w")

    def _build_run_bar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(4, 4))
        self.run_button = ctk.CTkButton(bar, text="Run pipeline", height=40, font=ctk.CTkFont(size=14, weight="bold"), command=self._start_run)
        self.run_button.pack(side="left")
        self.stop_button = ctk.CTkButton(bar, text="Stop", height=40, width=90, fg_color="#8a2f2f", hover_color="#6e2525", command=self._stop_run, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.open_output_button = ctk.CTkButton(bar, text="Open output folder", height=40, width=160, command=self._open_output_dir)
        self.open_output_button.pack(side="left", padx=8)
        self.progress = ctk.CTkProgressBar(bar, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=16)
        self.status_label = ctk.CTkLabel(self, text="Idle", text_color="gray70")
        self.status_label.pack(anchor="w", padx=20)

    def _build_log_panel(self):
        log_frame = ctk.CTkFrame(self, corner_radius=12)
        log_frame.pack(fill="both", expand=False, padx=16, pady=(4, 16))
        ctk.CTkLabel(log_frame, text="Log", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=16, pady=(10, 0))
        self.log_box = ctk.CTkTextbox(log_frame, height=180, font=ctk.CTkFont(family="Courier", size=12))
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self.log_box.configure(state="disabled")

    # -------------------------------------------------------------- pickers

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

    def _open_output_dir(self):
        out = Path(self.output_dir.get())
        out.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(out)])
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", str(out)])
        else:
            subprocess.run(["xdg-open", str(out)])

    # ------------------------------------------------------------ clip rows

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

    # ------------------------------------------------------------------ run

    def _resolve_csv_path(self) -> Path | None:
        if self.clip_table.get_children():
            return self._write_table_to_csv()
        if self.csv_path.get().strip():
            return Path(self.csv_path.get().strip())
        return None

    def _build_command(self) -> list[str] | None:
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

        cmd = [sys.executable, str(PIPELINE_SCRIPT), video, str(csv_path), "-o", self.output_dir.get().strip()]

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

        # run_pipeline.py always transcribes + burns captions as its last
        # step (no flag to skip it), so these are sent on every run.
        cmd += ["--language", self.language.get()]
        cmd += ["--model", self.model.get()]
        cmd += ["--caption-style", self.caption_style.get()]
        cmd += ["--position", self.position.get()]
        cmd += ["--text-color", self.text_color.get() or "white"]
        cmd += ["--highlight-color", self.highlight_color.get() or "yellow"]
        if self.all_caps.get():
            cmd.append("--all-caps")
        if self.box_highlight.get():
            cmd.append("--box")

        return cmd

    def _start_run(self):
        if self.process is not None:
            return
        cmd = self._build_command()
        if cmd is None:
            return

        self._clear_log()
        self._append_log("$ " + " ".join(cmd) + "\n\n")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start()
        self.status_label.configure(text="Running…")

        thread = threading.Thread(target=self._run_subprocess, args=(cmd,), daemon=True)
        thread.start()

    def _run_subprocess(self, cmd):
        try:
            self.process = subprocess.Popen(
                cmd, cwd=str(REPO_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in self.process.stdout:
                self.log_queue.put(line)
            return_code = self.process.wait()
        except Exception as exc:  # surfaced in the log panel, not a crash dialog
            self.log_queue.put(f"\n[GUI] Failed to launch pipeline: {exc}\n")
            return_code = -1
        finally:
            self.process = None
            self.log_queue.put(f"\n[GUI] Finished with exit code {return_code}\n")
            self.log_queue.put("__DONE__")

    def _stop_run(self):
        if self.process is not None:
            self.process.terminate()
            self._append_log("\n[GUI] Stop requested…\n")

    def _poll_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line == "__DONE__":
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.progress.stop()
                    self.status_label.configure(text="Idle")
                else:
                    self._append_log(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    # ------------------------------------------------------------------ log

    def _append_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


def main():
    if not PIPELINE_SCRIPT.exists():
        print(f"Can't find run_pipeline.py next to gui/ (expected at {PIPELINE_SCRIPT}).")
        sys.exit(1)
    app = ClipperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
