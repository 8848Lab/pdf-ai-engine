"""Apply the Merge A fixes of tasks 3..upto to <root>/engine/operations.py.

Usage: python stage_patch.py <root> <upto>   (upto in 2..7; 2 = no fixes)
"""
import sys
from pathlib import Path

root, upto = Path(sys.argv[1]), int(sys.argv[2])
path = root / "engine" / "operations.py"
src = path.read_text(encoding="utf-8")


def sub(old, new):
    global src
    assert src.count(old) == 1, f"anchor x{src.count(old)}: {old[:120]}"
    src = src.replace(old, new)


if upto >= 3:
    sub("from engine.document import Image, TextBlock\n",
        "from engine.document import Image, TextBlock\n"
        "from engine.geometry import OTHER_DRAWING, TEXT_DRAWING, at_rotation_zero, "
        "drawing_refusal, to_display_matrix, unrotated_bounds\n")
    sub("    if not rect.intersects(page.rect):\n", "    if not rect.intersects(unrotated_bounds(page)):\n")
    sub("    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, page.rect.x1))\n"
        "    y1 = max(rect.y1, min(rect.y0 + needed_height, page.rect.y1))\n",
        "    x1 = max(rect.x1, min(rect.x1 + _WIDTH_PRECISION_PAD_PT, unrotated_bounds(page).x1))\n"
        "    y1 = max(rect.y1, min(rect.y0 + needed_height, unrotated_bounds(page).y1))\n")
    sub("    if not destination_page.rect.contains(destination_rect):\n",
        "    if not unrotated_bounds(destination_page).contains(destination_rect):\n")
    sub("    if not page.rect.contains(rect):\n", "    if not unrotated_bounds(page).contains(rect):\n")
if upto >= 4:
    sub("    zoom = pixmap.width / page.rect.width\n", "    to_display = to_display_matrix(page)\n")
    sub("        x_px = max(0, min(pixmap.width - 1, int(x_pt * zoom)))\n"
        "        y_px = max(0, min(pixmap.height - 1, int(y_pt * zoom)))\n",
        "        display = fitz.Point(x_pt, y_pt) * to_display\n"
        "        x_px = max(0, min(pixmap.width - 1, int(display.x - pixmap.x)))\n"
        "        y_px = max(0, min(pixmap.height - 1, int(display.y - pixmap.y)))\n")
if upto >= 5:
    sub("    page.add_redact_annot(rect, fill=fill)\n    page.apply_redactions(images=2, graphics=1, text=0)\n",
        "    with at_rotation_zero(page):\n        page.add_redact_annot(rect, fill=fill)\n"
        "        page.apply_redactions(images=2, graphics=1, text=0)\n")
if upto >= 6:
    sub("        page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)\n",
        "        with at_rotation_zero(page):\n"
        "            page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)\n")
if upto >= 7:
    VB = "    page, rect = _validate_target(handle, page_index, bbox)\n"
    VT = "    page, rect = _validate_target(handle, page_index, target.bbox)\n"
    g = lambda p, i, k: f"    _refuse_unsupported_drawing({p}, {i}, {k})\n"
    sub(VB + "    _erase_region(page, rect, fill=(0, 0, 0))\n",
        VB + g("page", "page_index", "OTHER_DRAWING") + "    _erase_region(page, rect, fill=(0, 0, 0))\n")
    sub(VT + "\n    if target.size <= 0:", VT + g("page", "page_index", "TEXT_DRAWING") + "\n    if target.size <= 0:")
    sub(VT + "    _clean_erase(page, rect)\n", VT + g("page", "page_index", "OTHER_DRAWING") + "    _clean_erase(page, rect)\n")
    sub("    source_page, source_rect = _validate_target(handle, page_index, target.bbox)\n",
        "    source_page, source_rect = _validate_target(handle, page_index, target.bbox)\n"
        + g("source_page", "page_index", "OTHER_DRAWING"))
    sub("    destination_page = handle[dest_index]\n", "")
    sub("    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)\n",
        "    destination_page, destination_rect = _validate_target(handle, dest_index, destination_bbox)\n"
        + g("destination_page", "dest_index", "TEXT_DRAWING"))
    sub(VB + "\n    if not unrotated_bounds(page).contains(rect):",
        VB + g("page", "page_index", "TEXT_DRAWING") + "\n    if not unrotated_bounds(page).contains(rect):")
    sub(VT + "\n    if target.xref == 0:", VT + g("page", "page_index", "OTHER_DRAWING") + "\n    if target.xref == 0:")
    sub("def _erase_region(",
        "def _refuse_unsupported_drawing(page, page_index, kind):\n"
        "    reason = drawing_refusal(page, page_index, kind)\n"
        "    if reason is not None:\n        raise ValueError(reason)\n\n\ndef _erase_region(")
path.write_text(src, encoding="utf-8")
