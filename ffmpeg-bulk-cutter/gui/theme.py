"""Shared color palette, fonts, and small style helpers for the Clipper Studio GUI."""
import customtkinter as ctk

BG = "#0b0d12"
SIDEBAR_BG = "#0f1117"
SURFACE = "#171a22"
SURFACE_ALT = "#1e2230"
BORDER = "#272c3a"

ACCENT = "#8b7bf7"
ACCENT_HOVER = "#7566e6"
ACCENT_SOFT = "#242043"

DANGER = "#e35d6a"
DANGER_HOVER = "#c9505c"

TEXT = "#f2f3f7"
TEXT_MUTED = "#9198ab"
TEXT_FAINT = "#5b6072"


def apply():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


def font(size=13, weight="normal"):
    return ctk.CTkFont(size=size, weight=weight)


def mono_font(size=12):
    return ctk.CTkFont(family="Courier", size=size)


def title_font(size=22):
    return ctk.CTkFont(size=size, weight="bold")
