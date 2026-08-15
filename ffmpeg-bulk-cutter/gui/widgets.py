"""Reusable UI building blocks for the Clipper Studio GUI, shared across pages."""
import customtkinter as ctk

import theme

LANGUAGE_CHOICES = ["auto", "en", "hi", "hinglish"]
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
POSITION_CHOICES = ["bottom", "middle", "top"]


def card(parent, title, subtitle=None):
    """A rounded, bordered panel with a heading. Returns the inner body frame to fill in."""
    outer = ctk.CTkFrame(parent, corner_radius=14, fg_color=theme.SURFACE,
                          border_width=1, border_color=theme.BORDER)
    outer.pack(fill="x", padx=0, pady=(0, 16))

    head = ctk.CTkFrame(outer, fg_color="transparent")
    head.pack(fill="x", padx=20, pady=(18, 4))
    dot = ctk.CTkFrame(head, width=6, height=6, corner_radius=3, fg_color=theme.ACCENT)
    dot.pack(side="left", pady=4)
    dot.pack_propagate(False)
    ctk.CTkLabel(head, text=title, font=theme.font(15, "bold"), text_color=theme.TEXT).pack(side="left", padx=(10, 0))
    if subtitle:
        ctk.CTkLabel(outer, text=subtitle, font=theme.font(12), text_color=theme.TEXT_MUTED,
                     wraplength=760, justify="left").pack(anchor="w", padx=20, pady=(0, 4))

    body = ctk.CTkFrame(outer, fg_color="transparent")
    body.pack(fill="x", padx=20, pady=(8, 20))
    return body


def field_row(parent, label_text, width=150):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=5)
    ctk.CTkLabel(row, text=label_text, width=width, anchor="w",
                 text_color=theme.TEXT_MUTED, font=theme.font(12)).pack(side="left")
    return row


def primary_button(parent, text, command, width=170):
    return ctk.CTkButton(parent, text=text, command=command, height=40, width=width,
                          font=theme.font(14, "bold"), fg_color=theme.ACCENT,
                          hover_color=theme.ACCENT_HOVER, corner_radius=10)


def danger_button(parent, text, command, width=90):
    return ctk.CTkButton(parent, text=text, command=command, height=40, width=width,
                          font=theme.font(13, "bold"), fg_color=theme.DANGER,
                          hover_color=theme.DANGER_HOVER, corner_radius=10, state="disabled")


def ghost_button(parent, text, command, width=110):
    return ctk.CTkButton(parent, text=text, command=command, height=32, width=width,
                          font=theme.font(12), fg_color=theme.SURFACE_ALT,
                          hover_color=theme.BORDER, corner_radius=8,
                          border_width=1, border_color=theme.BORDER)


def entry(parent, textvariable=None, placeholder=None, width=None):
    kwargs = dict(fg_color=theme.SURFACE_ALT, border_color=theme.BORDER, border_width=1,
                  corner_radius=8, text_color=theme.TEXT)
    if width:
        kwargs["width"] = width
    if textvariable is not None:
        kwargs["textvariable"] = textvariable
    if placeholder:
        kwargs["placeholder_text"] = placeholder
    return ctk.CTkEntry(parent, **kwargs)


def option_menu(parent, values, variable, width=120):
    return ctk.CTkOptionMenu(parent, values=values, variable=variable, width=width,
                              fg_color=theme.SURFACE_ALT, button_color=theme.ACCENT,
                              button_hover_color=theme.ACCENT_HOVER, corner_radius=8)


def checkbox(parent, text, variable):
    return ctk.CTkCheckBox(parent, text=text, variable=variable, font=theme.font(12),
                            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                            border_color=theme.BORDER, text_color=theme.TEXT)


class CaptionOptionsPanel(ctk.CTkFrame):
    """Language / model / caption-style / colors — shared by the pipeline and templates pages."""

    def __init__(self, parent, *, style_choices, default_style, default_position="bottom"):
        super().__init__(parent, fg_color="transparent")
        self.language = ctk.StringVar(value="auto")
        self.model = ctk.StringVar(value="small")
        self.caption_style = ctk.StringVar(value=default_style)
        self.position = ctk.StringVar(value=default_position)
        self.text_color = ctk.StringVar(value="white")
        self.highlight_color = ctk.StringVar(value="yellow")
        self.all_caps = ctk.BooleanVar(value=False)
        self.box_highlight = ctk.BooleanVar(value=False)
        self.use_groq = ctk.BooleanVar(value=False)
        self.groq_api_key = ctk.StringVar(value="")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x")

        def cell(r, c, label, widget):
            ctk.CTkLabel(grid, text=label, text_color=theme.TEXT_MUTED, font=theme.font(12)).grid(
                row=r, column=c * 2, sticky="w", padx=(0 if c == 0 else 18, 6), pady=6)
            widget.grid(row=r, column=c * 2 + 1, sticky="w", pady=6)

        cell(0, 0, "Language", option_menu(grid, LANGUAGE_CHOICES, self.language, width=110))
        cell(0, 1, "Whisper model", option_menu(grid, MODEL_CHOICES, self.model, width=110))
        cell(0, 2, "Style", option_menu(grid, style_choices, self.caption_style, width=110))

        cell(1, 0, "Position", option_menu(grid, POSITION_CHOICES, self.position, width=110))
        cell(1, 1, "Text color", entry(grid, textvariable=self.text_color, width=110))
        cell(1, 2, "Highlight color", entry(grid, textvariable=self.highlight_color, width=110))

        toggles = ctk.CTkFrame(self, fg_color="transparent")
        toggles.pack(fill="x", pady=(10, 0))
        checkbox(toggles, "ALL CAPS", self.all_caps).pack(side="left")
        checkbox(toggles, "Highlight box", self.box_highlight).pack(side="left", padx=20)

        groq_row = ctk.CTkFrame(self, fg_color="transparent")
        groq_row.pack(fill="x", pady=(10, 0))
        checkbox(groq_row, "Use Groq API (paid, faster)", self.use_groq).pack(side="left")
        entry(groq_row, textvariable=self.groq_api_key, placeholder="Groq API key (or set GROQ_API_KEY)", width=280).pack(
            side="left", padx=(14, 0))

    def as_args(self) -> list[str]:
        args = [
            "--language", self.language.get(),
            "--model", self.model.get(),
            "--caption-style", self.caption_style.get(),
            "--position", self.position.get(),
            "--text-color", self.text_color.get() or "white",
            "--highlight-color", self.highlight_color.get() or "yellow",
        ]
        if self.all_caps.get():
            args.append("--all-caps")
        if self.box_highlight.get():
            args.append("--box")
        if self.use_groq.get():
            args.append("--groq")
            if self.groq_api_key.get().strip():
                args += ["--groq-api-key", self.groq_api_key.get().strip()]
        return args
