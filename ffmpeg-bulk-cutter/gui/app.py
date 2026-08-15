#!/usr/bin/env python3
"""Desktop GUI for the FFmpeg Bulk Cutter toolkit.

Two workflows, one window:
  - Cut & Process : raw video -> cut clips -> silence removal -> reframe -> captions
                    (wraps run_pipeline.py)
  - Reel Templates: already-cut clips -> one of your three branded reel layouts
                    (wraps template_compose.py / template_ntfp1.py / template_ntfb2_blur.py)

Run with:
    python gui/app.py
(see ../run_gui.sh / ../run_gui.bat for a one-click launcher)
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk

import theme
from widgets import danger_button, primary_button
from pages.pipeline_page import PipelinePage
from pages.templates_page import TemplatesPage

REPO_DIR = Path(__file__).resolve().parent.parent

PAGES = [PipelinePage, TemplatesPage]

theme.apply()


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, on_select):
        super().__init__(parent, width=220, fg_color=theme.SIDEBAR_BG, corner_radius=0)
        self.pack_propagate(False)
        self.on_select = on_select
        self.buttons = {}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(28, 4))
        ctk.CTkLabel(header, text="Clipper Studio", font=theme.title_font(19),
                     text_color=theme.TEXT).pack(anchor="w")
        ctk.CTkLabel(header, text="ffmpeg bulk cutter", font=theme.font(11),
                     text_color=theme.TEXT_FAINT).pack(anchor="w")

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=12, pady=(24, 0))
        for page_cls in PAGES:
            btn = ctk.CTkButton(
                nav, text=page_cls.title, anchor="w", height=42, corner_radius=10,
                font=theme.font(13, "bold"), fg_color="transparent", text_color=theme.TEXT_MUTED,
                hover_color=theme.SURFACE_ALT,
                command=lambda p=page_cls: self.on_select(p),
            )
            btn.pack(fill="x", pady=3)
            self.buttons[page_cls] = btn

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER).pack(fill="x", padx=16, pady=16)
        self.hint = ctk.CTkLabel(
            self, text="Runs entirely on your machine — no upload, no cloud.",
            font=theme.font(11), text_color=theme.TEXT_FAINT, wraplength=180, justify="left",
        )
        self.hint.pack(anchor="w", padx=20)

    def set_active(self, page_cls):
        for cls, btn in self.buttons.items():
            active = cls is page_cls
            btn.configure(fg_color=theme.ACCENT_SOFT if active else "transparent",
                          text_color=theme.TEXT if active else theme.TEXT_MUTED)


class ClipperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Clipper Studio")
        self.geometry("1100x900")
        self.minsize(940, 680)
        self.configure(fg_color=theme.BG)

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = Sidebar(self, self._show_page)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="ns")

        content_shell = ctk.CTkFrame(self, fg_color="transparent")
        content_shell.grid(row=0, column=1, sticky="nsew", padx=24, pady=(24, 0))
        content_shell.grid_columnconfigure(0, weight=1)
        content_shell.grid_rowconfigure(2, weight=1)

        self.page_header = ctk.CTkLabel(content_shell, text="", font=theme.title_font(24), text_color=theme.TEXT)
        self.page_header.grid(row=0, column=0, sticky="w")
        self.page_blurb = ctk.CTkLabel(content_shell, text="", font=theme.font(13), text_color=theme.TEXT_MUTED)
        self.page_blurb.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.scroll = ctk.CTkScrollableFrame(content_shell, fg_color="transparent")
        self.scroll.grid(row=2, column=0, sticky="nsew", pady=(16, 0))

        self.pages = {}
        for page_cls in PAGES:
            page = page_cls(self.scroll, REPO_DIR)
            self.pages[page_cls] = page

        bottom = ctk.CTkFrame(self, fg_color=theme.SIDEBAR_BG, corner_radius=0)
        bottom.grid(row=1, column=1, sticky="ew")
        self._build_run_bar(bottom)

        self.active_page_cls = PAGES[0]
        self._show_page(PAGES[0])
        self.after(100, self._poll_log_queue)

    # ------------------------------------------------------------------ nav
    def _show_page(self, page_cls):
        for cls, page in self.pages.items():
            if cls is page_cls:
                page.pack(fill="x")
            else:
                page.pack_forget()
        self.active_page_cls = page_cls
        self.sidebar.set_active(page_cls)
        self.page_header.configure(text=page_cls.title)
        self.page_blurb.configure(text=self.pages[page_cls].blurb)
        self.run_button.configure(text=self.pages[page_cls].run_label)

    # -------------------------------------------------------------- run bar
    def _build_run_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=16)

        controls = ctk.CTkFrame(bar, fg_color="transparent")
        controls.pack(fill="x")
        self.run_button = primary_button(controls, "Run pipeline", self._start_run)
        self.run_button.pack(side="left")
        self.stop_button = danger_button(controls, "Stop", self._stop_run)
        self.stop_button.pack(side="left", padx=8)
        self.open_output_button = ctk.CTkButton(
            controls, text="Open output folder", height=40, width=160, command=self._open_output_dir,
            fg_color=theme.SURFACE_ALT, hover_color=theme.BORDER, corner_radius=10,
            border_width=1, border_color=theme.BORDER, text_color=theme.TEXT,
        )
        self.open_output_button.pack(side="left", padx=8)
        self.progress = ctk.CTkProgressBar(controls, mode="indeterminate", progress_color=theme.ACCENT,
                                            fg_color=theme.SURFACE_ALT)
        self.progress.pack(side="left", fill="x", expand=True, padx=16)
        self.status_label = ctk.CTkLabel(bar, text="Idle", text_color=theme.TEXT_FAINT, font=theme.font(11))
        self.status_label.pack(anchor="w", pady=(8, 0))

        log_frame = ctk.CTkFrame(parent, corner_radius=14, fg_color=theme.SURFACE,
                                  border_width=1, border_color=theme.BORDER)
        log_frame.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(log_frame, text="Log", font=theme.font(13, "bold"), text_color=theme.TEXT_MUTED).pack(
            anchor="w", padx=16, pady=(10, 0))
        self.log_box = ctk.CTkTextbox(log_frame, height=150, font=theme.mono_font(12),
                                       fg_color=theme.SURFACE, text_color=theme.TEXT_MUTED,
                                       border_width=0)
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(4, 16))
        self.log_box.configure(state="disabled")

    def _open_output_dir(self):
        out = Path(self.pages[self.active_page_cls].output_dir.get())
        out.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.run(["open", str(out)])
        elif sys.platform.startswith("win"):
            subprocess.run(["explorer", str(out)])
        else:
            subprocess.run(["xdg-open", str(out)])

    # ------------------------------------------------------------------ run
    def _start_run(self):
        if self.process is not None:
            return
        cmd = self.pages[self.active_page_cls].build_command()
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
        except Exception as exc:
            self.log_queue.put(f"\n[GUI] Failed to launch: {exc}\n")
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
    if not (REPO_DIR / "run_pipeline.py").exists():
        print(f"Can't find run_pipeline.py next to gui/ (expected under {REPO_DIR}).")
        sys.exit(1)
    app = ClipperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
