"""Reel templates — template_compose.py / template_ntfp1.py / template_ntfb2_blur.py."""
import sys
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

import theme
from widgets import CaptionOptionsPanel, card, checkbox, entry, field_row, ghost_button

TEMPLATES = {
    "boxed": {
        "label": "Boxed",
        "script": "template_compose.py",
        "description": (
            "The full, uncropped video sits letterboxed in a fixed box over a faintly "
            "textured dark background, with captions in their own space below it — "
            "never overlapping the video."
        ),
        "default_position": "top",
    },
    "fullscreen": {
        "label": "Fullscreen Fade",
        "script": "template_ntfp1.py",
        "description": (
            "A near-fullscreen video, cropped edge-to-edge with automatic face tracking, "
            "under a plain grid-textured top margin — fading softly into the background "
            "at the bottom edge instead of a hard cut."
        ),
        "default_position": "bottom",
    },
    "blurred": {
        "label": "Blurred Backdrop",
        "script": "template_ntfb2_blur.py",
        "description": (
            "The classic 'blurred backdrop' look: the full landscape video plays sharp and "
            "letterboxed in the middle, with the same video blurred and scaled up to fill "
            "the rest of the canvas behind it (Spotify Canvas style)."
        ),
        "default_position": "bottom",
    },
}


class TemplatesPage(ctk.CTkFrame):
    title = "Reel Templates"
    run_label = "Render template"
    blurb = "Compose already-cut clips into one of your branded reel layouts, with captions burned in."

    def __init__(self, parent, repo_dir: Path):
        super().__init__(parent, fg_color="transparent")
        self.repo_dir = repo_dir

        self.selected = ctk.StringVar(value="boxed")
        self.input_path = ctk.StringVar()
        self.input_is_folder = ctk.BooleanVar(value=False)
        self.output_dir = ctk.StringVar(value=str(Path.cwd() / "template_output"))
        self.no_gpu = ctk.BooleanVar(value=False)
        self.no_captions = ctk.BooleanVar(value=False)

        self.opt_vars = {}
        self.caption_panel = None

        self._build()
        self._on_template_change("boxed")

    def _build(self):
        body = card(self, "1 · Pick a template")
        seg = ctk.CTkSegmentedButton(
            body, values=[TEMPLATES[k]["label"] for k in TEMPLATES],
            fg_color=theme.SURFACE_ALT, selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER, unselected_color=theme.SURFACE_ALT,
            command=self._on_segment_click,
        )
        seg.set(TEMPLATES["boxed"]["label"])
        seg.pack(anchor="w", pady=(0, 10))
        self.description_label = ctk.CTkLabel(body, text="", text_color=theme.TEXT_MUTED,
                                               font=theme.font(12), wraplength=760, justify="left")
        self.description_label.pack(anchor="w")

        body = card(self, "2 · Input", "A single video, or a whole folder of already-cut clips.")
        type_row = ctk.CTkFrame(body, fg_color="transparent")
        type_row.pack(fill="x", pady=(0, 8))
        ctk.CTkRadioButton(type_row, text="Single video file", variable=self.input_is_folder, value=False,
                           fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                           text_color=theme.TEXT).pack(side="left")
        ctk.CTkRadioButton(type_row, text="Folder of clips", variable=self.input_is_folder, value=True,
                           fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                           text_color=theme.TEXT).pack(side="left", padx=20)
        row = field_row(body, "Path")
        entry(row, textvariable=self.input_path, placeholder="video file or clips folder").pack(
            side="left", fill="x", expand=True)
        ghost_button(row, "Browse", self._pick_input).pack(side="left", padx=(10, 0))

        body = card(self, "3 · Output folder")
        row = field_row(body, "Save results to")
        entry(row, textvariable=self.output_dir).pack(side="left", fill="x", expand=True)
        ghost_button(row, "Browse", self._pick_output_dir).pack(side="left", padx=(10, 0))

        self.options_card_body = card(self, "4 · Template layout")
        self.options_container = ctk.CTkFrame(self.options_card_body, fg_color="transparent")
        self.options_container.pack(fill="x")

        common_row = ctk.CTkFrame(self.options_card_body, fg_color="transparent")
        common_row.pack(fill="x", pady=(12, 0))
        checkbox(common_row, "Force CPU (--no-gpu)", self.no_gpu).pack(side="left")
        checkbox(common_row, "Skip captions (compose only)", self.no_captions).pack(side="left", padx=20)

        self.caption_card_body = card(self, "5 · Captions")
        self.caption_container = ctk.CTkFrame(self.caption_card_body, fg_color="transparent")
        self.caption_container.pack(fill="x")

    # -- template switching ------------------------------------------------
    def _on_segment_click(self, label):
        key = next(k for k, v in TEMPLATES.items() if v["label"] == label)
        self._on_template_change(key)

    def _on_template_change(self, key):
        self.selected.set(key)
        info = TEMPLATES[key]
        self.description_label.configure(text=info["description"])
        self._rebuild_options(key)
        self._rebuild_captions(info["default_position"])

    def _rebuild_options(self, key):
        for child in self.options_container.winfo_children():
            child.destroy()
        vars_for_key = {}

        def num_field(row, label, default, width=90):
            var = ctk.StringVar(value=default)
            ctk.CTkLabel(row, text=label, text_color=theme.TEXT_MUTED, font=theme.font(12)).pack(
                side="left", padx=(0, 6))
            entry(row, textvariable=var, width=width).pack(side="left", padx=(0, 18))
            return var

        row = ctk.CTkFrame(self.options_container, fg_color="transparent")
        row.pack(fill="x")

        if key == "boxed":
            vars_for_key["zoom"] = num_field(row, "Zoom (1.0 = full frame)", "1.0")
        elif key == "fullscreen":
            vars_for_key["video_y"] = num_field(row, "Video Y", "380")
            vars_for_key["video_h"] = num_field(row, "Video height", "1450")
            vars_for_key["fade_h"] = num_field(row, "Fade height", "140")
            row2 = ctk.CTkFrame(self.options_container, fg_color="transparent")
            row2.pack(fill="x", pady=(8, 0))
            vars_for_key["gpu_detect"] = ctk.BooleanVar(value=False)
            checkbox(row2, "Try GPU face detection (experimental)", vars_for_key["gpu_detect"]).pack(anchor="w")
        elif key == "blurred":
            vars_for_key["blur_sigma"] = num_field(row, "Blur strength", "20")
            vars_for_key["video_y"] = num_field(row, "Video Y (blank = centered)", "")

        self.opt_vars = vars_for_key

    def _rebuild_captions(self, default_position):
        for child in self.caption_container.winfo_children():
            child.destroy()
        self.caption_panel = CaptionOptionsPanel(
            self.caption_container, style_choices=["word", "highlight"],
            default_style="highlight", default_position=default_position,
        )
        self.caption_panel.pack(fill="x")

    # -- pickers -------------------------------------------------------------
    def _pick_input(self):
        if self.input_is_folder.get():
            path = filedialog.askdirectory(title="Choose folder of clips")
        else:
            path = filedialog.askopenfilename(title="Choose a video file",
                                               filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")])
        if path:
            self.input_path.set(path)

    def _pick_output_dir(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_dir.set(path)

    # -- command building ------------------------------------------------
    def build_command(self):
        input_path = self.input_path.get().strip()
        if not input_path:
            messagebox.showerror("Missing input", "Pick a video file or a folder of clips first.")
            return None
        if not Path(input_path).exists():
            messagebox.showerror("Not found", f"Can't find:\n{input_path}")
            return None

        key = self.selected.get()
        info = TEMPLATES[key]
        script_path = self.repo_dir / info["script"]
        cmd = [sys.executable, str(script_path), input_path, "-o", self.output_dir.get().strip()]

        if key == "boxed":
            zoom = self.opt_vars["zoom"].get().strip() or "1.0"
            cmd += ["--zoom", zoom]
        elif key == "fullscreen":
            cmd += ["--video-y", self.opt_vars["video_y"].get().strip() or "380"]
            cmd += ["--video-h", self.opt_vars["video_h"].get().strip() or "1450"]
            cmd += ["--fade-h", self.opt_vars["fade_h"].get().strip() or "140"]
            if self.opt_vars["gpu_detect"].get():
                cmd.append("--gpu-detect")
        elif key == "blurred":
            cmd += ["--blur-sigma", self.opt_vars["blur_sigma"].get().strip() or "20"]
            video_y = self.opt_vars["video_y"].get().strip()
            if video_y:
                cmd += ["--video-y", video_y]

        if self.no_gpu.get():
            cmd.append("--no-gpu")

        if self.no_captions.get():
            cmd.append("--no-captions")
        else:
            cmd += self.caption_panel.as_args()

        return cmd
