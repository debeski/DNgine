from __future__ import annotations

from micro_toolkit.core.theme import ThemePalette


def card_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return f"QFrame {{ background: {palette.surface_bg}; border: 1px solid {palette.border}; border-radius: {radius}px; }}"


def page_title_style(palette: ThemePalette, *, size: int = 30, weight: int = 800) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def section_title_style(palette: ThemePalette, *, size: int = 18, weight: int = 700) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def body_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def muted_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400, extra: str = "") -> str:
    suffix = f" {extra.strip()}" if extra and extra.strip() else ""
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_muted};{suffix}"
