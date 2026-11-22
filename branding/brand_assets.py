"""Wspólny model wektorowy znaku. Bez Cairo, renderPM i programów zewnętrznych."""
from functools import lru_cache
import os
from pathlib import Path
from xml.etree import ElementTree as ET

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent
NAME = "Otwarte AED"
SLOGAN = "Dane, które ratują minuty."
RED = "#D92638"
NAVY = "#0F2C59"
WHITE = "#FFFFFF"
LIGHT = "#F2F5FA"
SLATE = "#5C6B82"
WIDTH, HEIGHT = 700, 200
SYMBOL_HEIGHT = 160
MODULE = 32  # H/5, gdzie H jest mierzone po osi konturu pinezki.
CONCEPT = [
    "Znak łączy serce z impulsem EKG, wskazując na ratowniczy charakter kampanii.",
    "Kontur pinezki lokalizacyjnej podkreśla potrzebę szybkiego odnalezienia defibrylatora AED.",
    "Otwarty węzeł danych pokazuje, że informacja o urządzeniu może łączyć niezależne źródła i pozostawać dostępna do ponownego wykorzystania.",
    "Czerwień wyróżnia sygnał działania, a granat buduje skojarzenie z wiarygodną informacją publiczną.",
]
COLORS = [("Czerwień ratownicza", RED, "Podstawowy"), ("Granat zaufania", NAVY, "Podstawowy"),
          ("Biel", WHITE, "Uzupełniający"), ("Jasne tło", LIGHT, "Uzupełniający"),
          ("Szaroniebieski", SLATE, "Uzupełniający")]


def font_path(bold=False):
    override = os.getenv("AED_FONT_BOLD" if bold else "AED_FONT_REGULAR")
    candidates = [Path(override)] if override else []
    candidates += [Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
                   Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Brak fontu TTF. Ustaw AED_FONT_REGULAR i AED_FONT_BOLD na lokalne fonty z polskimi znakami.")


def text_path(text, x, baseline, size, bold=False):
    """Krzywe liter zamiast odwołań do fontu w końcowym SVG."""
    font = TTFont(font_path(bold))
    try:
        glyphs = font.getGlyphSet()
        cmap = font.getBestCmap()
        scale = size / font["head"].unitsPerEm
        pen = SVGPathPen(glyphs)
        for char in text:
            glyph_name = cmap[ord(char)]
            glyphs[glyph_name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
            x += font["hmtx"].metrics[glyph_name][0] * scale
        return pen.getCommands(), x
    finally:
        font.close()


@lru_cache(maxsize=1)
def components():
    paths = [
        {"d": "M90 170 C76 151 24 116 24 74 C24 37 54 10 90 10 C126 10 156 37 156 74 C156 116 104 151 90 170 Z", "fill": "none", "stroke": RED, "stroke-width": "8"},
        {"d": "M90 113 C77 103 51 87 51 66 C51 48 76 43 90 61 C104 43 129 48 129 66 C129 87 103 103 90 113 Z", "fill": NAVY},
        {"d": "M56 79 L73 79 L81 62 L91 94 L101 73 L124 73", "fill": "none", "stroke": WHITE, "stroke-width": "5"},
        {"d": "M125 106 L140 117", "fill": "none", "stroke": NAVY, "stroke-width": "6"},
        # Biały poddruk oddziela otwarty węzeł od konturu pinezki.
        {"d": "M171 126 C171 137 162 146 151 146 C140 146 131 137 131 126 C131 115 140 106 151 106 C162 106 171 115 171 126 Z", "fill": WHITE},
        {"d": "M151 110 C142 110 135 117 135 126 C135 135 142 142 151 142 C160 142 167 135 167 126", "fill": "none", "stroke": NAVY, "stroke-width": "6"},
        {"d": "M171 113 C171 115.2 169.2 117 167 117 C164.8 117 163 115.2 163 113 C163 110.8 164.8 109 167 109 C169.2 109 171 110.8 171 113 Z", "fill": RED},
    ]
    name, end = text_path("Otwarte ", 202, 109, 75, bold=True)
    aed, _ = text_path("AED", end, 109, 75, bold=True)
    slogan, _ = text_path(SLOGAN, 204, 156, 27)
    return paths + [{"d": name, "fill": NAVY}, {"d": aed, "fill": RED}, {"d": slogan, "fill": NAVY}]


def svg_bytes(*, replacements=None, symbol_only=False):
    replacements = replacements or {}
    attrs = {"xmlns": "http://www.w3.org/2000/svg", "width": str(180 if symbol_only else WIDTH), "height": str(HEIGHT),
             "viewBox": f"0 0 {180 if symbol_only else WIDTH} {HEIGHT}", "role": "img", "aria-labelledby": "title desc"}
    root = ET.Element("svg", attrs)
    ET.SubElement(root, "title", {"id": "title"}).text = NAME
    ET.SubElement(root, "desc", {"id": "desc"}).text = "Serce z impulsem EKG w pinezce lokalizacji, połączone z otwartym węzłem danych. " + SLOGAN
    for component in (components()[:7] if symbol_only else components()):
        item = {key: replacements.get(value, value) for key, value in component.items()}
        if "stroke" in item:
            item.update({"stroke-linecap": "round", "stroke-linejoin": "round"})
        ET.SubElement(root, "path", item)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def rgb(hex_color):
    return tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))


def cmyk(hex_color):
    red, green, blue = [v / 255 for v in rgb(hex_color)]
    key = 1 - max(red, green, blue)
    if key == 1:
        return (0.0, 0.0, 0.0, 100.0)
    return tuple(round((1 - value - key) / (1 - key) * 100, 1) for value in (red, green, blue)) + (round(key * 100, 1),)


def write_logo():
    path = ROOT / "logo_otwarte_aed.svg"
    path.write_bytes(svg_bytes())
    return path
