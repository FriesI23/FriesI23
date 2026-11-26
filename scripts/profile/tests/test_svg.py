from xml.etree import ElementTree

import pytest

from profile_badges.svg import render


def test_flat_square_layout_and_palette():
    doc = ElementTree.fromstring(render("apps", "2", "blue"))
    assert doc.get("role") == "img" and doc.get("aria-label") == "apps: 2"
    assert doc.findtext("{*}title") == "apps: 2"
    assert float(doc.get("width")) == 54 and doc.get("height") == "20"
    rects = doc.findall(".//{*}rect")
    assert [
        (float(rect.get("width")), rect.get("fill")) for rect in rects
    ] == [
        (37, "#555"),
        (17, "#007ec6"),
    ]
    assert not any(rect.get("rx") for rect in rects)
    assert doc.find(".//{*}linearGradient") is None
    assert [
        (node.text, node.get("y")) for node in doc.findall(".//{*}text")
    ] == [
        ("apps", "140"),
        ("2", "140"),
    ]


def test_xml_escape_and_contrast():
    doc = ElementTree.fromstring(render("<a>&", "\"'", "#fbb040"))
    assert doc.get("aria-label") == "<a>&: \"'"
    assert doc.findtext("{*}title") == doc.get("aria-label")
    assert doc.findall(".//{*}text")[-1].get("fill") == "#333"


def test_label_free_geometry_and_whitespace_trim():
    doc = ElementTree.fromstring(render("  ", "  next  ", "FFF"))
    assert doc.get("aria-label") == "next"
    rects = [
        rect
        for rect in doc.findall(".//{*}rect")
        if float(rect.get("width")) > 0
    ]
    assert len(rects) == 1 and rects[0].get("fill") == "#fff"
    assert [node.text for node in doc.findall(".//{*}text")] == ["next"]


def test_rejects_invalid_color_and_xml():
    with pytest.raises(ValueError, match="color"):
        render("test", "value", "not a color")
    with pytest.raises(ValueError, match="invalid XML"):
        render("test", "a\x00b", "blue")
