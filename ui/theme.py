"""Light / dark theme switch.

Streamlit has no Python API to change the theme at runtime, but since 1.5x
its main menu exposes a native System / Light / Dark switcher. This widget
drives that switcher from a two-icon toggle (sun / moon, drawn in CSS: the
HTML sanitiser strips inline SVG):

* no page reload — the session (and the user's login) is preserved;
* the choice is persisted by Streamlit itself (browser local storage);
* both palettes are defined in ``.streamlit/config.toml``.

If a future Streamlit release renames the menu items, the toggle simply
does nothing and the native menu (⋮ top right) keeps working.
"""

from __future__ import annotations

import streamlit as st

_TEMPLATE = """
<style>
#{id} {{display: inline-flex; gap: 2px; padding: 3px; border-radius: 999px;
  border: 1px solid color-mix(in srgb, currentColor 28%, transparent);
  background: color-mix(in srgb, currentColor 6%, transparent);}}
#{id} button {{all: unset; cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 26px; border-radius: 999px; color: inherit; opacity: .6; transition: all .15s ease;}}
#{id} button:hover {{opacity: 1;}}
#{id} button:focus-visible {{outline: 2px solid #1F6E57; outline-offset: 1px;}}
#{id} button.on {{background: #1F6E57; color: #F2EEE4; opacity: 1;}}
#{id} .sun {{width: 6px; height: 6px; border-radius: 50%; background: currentColor;
  box-shadow: 0 -6px 0 -1.5px currentColor, 0 6px 0 -1.5px currentColor, 6px 0 0 -1.5px currentColor,
    -6px 0 0 -1.5px currentColor, 4.3px 4.3px 0 -1.5px currentColor, -4.3px -4.3px 0 -1.5px currentColor,
    4.3px -4.3px 0 -1.5px currentColor, -4.3px 4.3px 0 -1.5px currentColor;}}
#{id} .moon {{width: 12px; height: 12px; border-radius: 50%; box-shadow: inset -4px -2px 0 0 currentColor;
  transform: rotate(-20deg);}}
</style>
<div id="{id}" role="group" aria-label="Thème">
  <button type="button" data-mode="Light" aria-label="Thème clair" title="Thème clair"><span class="sun"></span></button>
  <button type="button" data-mode="Dark" aria-label="Thème sombre" title="Thème sombre"><span class="moon"></span></button>
</div>
<script>
(() => {{
  const box = document.getElementById("{id}");
  if (!box) return;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const isDark = () => {{
    const el = document.querySelector('[data-testid="stApp"]') || document.body;
    const rgb = (getComputedStyle(el).backgroundColor.match(/\\d+/g) || [255, 255, 255]).map(Number);
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2] < 128;
  }};
  const paint = () => {{
    const dark = isDark();
    // Theme-dependent CSS variables (ui/style.py) key off this attribute.
    document.documentElement.dataset.poTheme = dark ? "dark" : "light";
    document.querySelectorAll('[id^="po-theme-"] button').forEach((b) =>
      b.classList.toggle("on", (b.dataset.mode === "Dark") === dark));
  }};
  const pick = async (mode) => {{
    const menu = document.querySelector('[data-testid="stMainMenuButton"]');
    if (!menu) return;
    menu.click();
    for (let i = 0; i < 40; i++) {{
      const item = document.querySelector(`[data-testid="stMainMenuItem-theme-${{mode}}"]`);
      if (item) {{ item.click(); break; }}
      await sleep(25);
    }}
    await sleep(30);
    if (document.querySelector('[data-testid="stMainMenuPopover"]')) menu.click();
    for (let i = 0; i < 10; i++) {{ await sleep(40); paint(); }}
  }};
  box.querySelectorAll("button").forEach((b) => (b.onclick = () => pick(b.dataset.mode)));
  paint();
  // Stay in sync if the theme is changed from Streamlit's own menu.
  if (!window.__poThemeSync) {{ window.__poThemeSync = setInterval(paint, 1200); }}
}})();
</script>
"""


def theme_toggle(key: str = "sidebar") -> None:
    """Render the light / dark icon toggle. ``key`` must be unique per page location."""
    st.html(_TEMPLATE.format(id=f"po-theme-{key}"), unsafe_allow_javascript=True)
