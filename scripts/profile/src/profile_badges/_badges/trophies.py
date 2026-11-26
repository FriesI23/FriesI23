"""Download and validate the light and dark trophy artwork."""

import re
from urllib.parse import urlencode
from xml.etree import ElementTree


def valid_trophy(svg):
    """Require a self-contained SVG with award artwork and a score."""
    if not isinstance(svg, str) or re.search(
        r"<!DOCTYPE|<\?xml-stylesheet", svg, re.I
    ):
        return False
    try:
        document = ElementTree.fromstring(svg)
    except (ElementTree.ParseError, ValueError):
        return False
    ns = "{http://www.w3.org/2000/svg}"
    if document.tag != ns + "svg":
        return False
    has_path = False
    has_score = False
    for node in document.iter():
        name = node.tag.rsplit("}", 1)[-1].lower()
        if name in {
            "script",
            "foreignobject",
            "set",
            "animate",
            "animatetransform",
            "animatemotion",
        }:
            return False
        for attribute, value in node.attrib.items():
            key = attribute.rsplit("}", 1)[-1].lower()
            if (
                key.startswith("on")
                or key in {"href", "src"}
                and not value.strip().startswith("#")
            ):
                return False
        css = " ".join(node.attrib.values()) + (
            " " + (node.text or "") if name == "style" else ""
        )
        if re.search(r"@import|url\(\s*[\"']?(?![\s\"'#])", css, re.I):
            return False
        if node.tag == ns + "path" and node.get("d"):
            has_path = True
        if node.tag == ns + "text" and re.fullmatch(
            r"[\d.,]+[kMGT]?pt", (node.text or "").strip(), re.I
        ):
            has_score = True
    return has_path and has_score


def update_trophies(*, root, trophy, owner, download_svg, write_svg):
    """Refresh both themes and report any retained artwork."""
    warnings = []
    rank = trophy["rank"]
    for theme in ("light", "dark"):
        path = f"profile/trophies/{theme}.svg"
        params = {
            "username": owner.lower(),
            "row": trophy["row"],
            "column": trophy["column"],
        }
        if theme == "dark":
            params["theme"] = trophy["dark_theme"]
        params["rank"] = ",".join(rank) if isinstance(rank, list) else rank
        try:
            svg = download_svg(trophy["url"] + "?" + urlencode(params))
            if not valid_trophy(svg):
                raise ValueError("response contains no valid trophy artwork")
        except Exception as exc:
            old = root / path
            if not old.is_file() or not valid_trophy(
                old.read_text(encoding="utf-8")
            ):
                raise ValueError(
                    f"{theme} trophy: no valid artwork available"
                ) from exc
            warnings.append(f"{theme} trophy: {exc}")
            continue
        write_svg(path, svg)
    return warnings
