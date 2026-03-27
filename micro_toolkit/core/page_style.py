from __future__ import annotations

from micro_toolkit.core.theme import ThemePalette


def surface_style(palette: ThemePalette, *, radius: int = 18, selector: str = "QFrame") -> str:
    return f"{selector} {{ background: {palette.surface_bg}; border: none; border-radius: {radius}px; }}"


def card_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QFrame")


def widget_card_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QWidget")


def label_surface_style(palette: ThemePalette, *, radius: int = 18) -> str:
    return surface_style(palette, radius=radius, selector="QLabel")


def tinted_card_style(
    palette: ThemePalette,
    *,
    background: str,
    border: str | None = None,
    radius: int = 22,
) -> str:
    _ = border or palette.border
    return f"QFrame {{ background: {background}; border: none; border-radius: {radius}px; }}"


def page_title_style(palette: ThemePalette, *, size: int = 30, weight: int = 800) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def section_title_style(palette: ThemePalette, *, size: int = 18, weight: int = 700) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def body_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400) -> str:
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_primary};"


def muted_text_style(palette: ThemePalette, *, size: int = 14, weight: int = 400, extra: str = "") -> str:
    suffix = f" {extra.strip()}" if extra and extra.strip() else ""
    return f"font-size: {size}px; font-weight: {weight}; color: {palette.text_muted};{suffix}"
