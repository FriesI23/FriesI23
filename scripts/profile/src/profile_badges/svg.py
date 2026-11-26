"""Render the profile's square Shields theme locally with badgepy."""

import re
from xml.dom.minidom import parseString
from xml.parsers.expat import ExpatError

from badgepy import badge
from badgepy.precalculated_text_measurer import PrecalculatedTextMeasurer

# Override badgepy's older palette with the current Shields colors.
_COLORS = {
    "brightgreen": "#4b0",
    "green": "#67ac09",
    "yellow": "#d8b800",
    "yellowgreen": "#95991a",
    "orange": "#ea7233",
    "red": "#dd4343",
    "blue": "#007ec6",
    "grey": "#555",
    "lightgrey": "#939393",
}
_ALIASES = {
    "gray": "grey",
    "lightgray": "lightgrey",
    "critical": "red",
    "important": "orange",
    "success": "brightgreen",
    "informational": "blue",
    "inactive": "lightgrey",
}


class _PixelAlignedText:
    """Align badgepy text widths to the Shields odd-pixel grid."""

    def text_width(self, text):
        width = PrecalculatedTextMeasurer.default().text_width(text)
        return (int(width / 10) | 1) * 10


def render(label: str, message: str, color: str) -> str:
    label, message, color = label.strip(), message.strip(), color.lower()
    color = _COLORS.get(_ALIASES.get(color, color), color).removeprefix("#")
    if not re.fullmatch(r"(?:[a-f0-9]{3}|[a-f0-9]{6})", color):
        raise ValueError(f"Unsupported badge color: {color}")
    title = f"{label}: {message}" if label else message
    try:
        svg = badge(
            left_text=label or message,
            right_text=message if label else None,
            left_color="#555" if label else "#" + color,
            right_color="#" + color,
            whole_title=title,
            style="flat-square",
            font_family="Verdana,Geneva,DejaVu Sans,sans-serif",
            measurer=_PixelAlignedText(),
        )
    except (ExpatError, UnicodeEncodeError) as error:
        raise ValueError(
            "Badge text contains an invalid XML character"
        ) from error

    # Apply the profile text contrast and remove shadows. Give the
    # image an accessible name for screen readers.
    doc = parseString(svg).documentElement
    doc.setAttribute("role", "img")
    doc.setAttribute("aria-label", title)
    backgrounds, text = doc.getElementsByTagName("g")
    backgrounds.setAttribute("shape-rendering", "crispEdges")
    text.setAttribute("text-rendering", "geometricPrecision")
    for shadow in text.getElementsByTagName("text"):
        if shadow.hasAttribute("fill-opacity"):
            text.removeChild(shadow)
    rgb = bytes.fromhex(
        "".join(c * 2 for c in color) if len(color) == 3 else color
    )
    brightness = (
        sum(v * weight for v, weight in zip(rgb, (299, 587, 114))) / 255000
    )
    if round(brightness, 2) > 0.69 and (message or not label):
        text.getElementsByTagName("text")[-1].setAttribute("fill", "#333")
    return doc.toxml()
