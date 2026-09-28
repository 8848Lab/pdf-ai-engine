"""Apply a W1+W2+W3 prototype to the scratch worktree (never the tracked repo).
Env WIDEN_PROTO=nowiden -> W1+W3 with R = own x1 (+pad); WIDEN_PROTO=widen -> W1+W2+W3;
unset -> today's code."""
import shutil
WT = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/critique-widen/wt"
assert "/scratchpad/critique-widen/wt" in WT

# document.py: optional origin/direction
p = f"{WT}/engine/document.py"; s = open(p).read()
s = s.replace("""    font: str
    size: float
""", """    font: str
    size: float
    origin: tuple[float, float] | None = None
    direction: tuple[float, float] | None = None
""", 1)
open(p, "w").write(s)

# parser.py: fill them
p = f"{WT}/engine/parser.py"; s = open(p).read()
s = s.replace("""                            size=span["size"],
                        )""", """                            size=span["size"],
                            origin=tuple(span["origin"]),
                            direction=tuple(line["dir"]),
                        )""", 1)
open(p, "w").write(s)

shutil.copy(f"{WT}/../w2proto.py", f"{WT}/engine/widen_proto.py")

# operations.py: new path in replace_text
p = f"{WT}/engine/operations.py"; s = open(p).read()
s = s.replace('import re\n', 'import os\nimport re\n', 1)
marker = "    # ---- geometry ----\n    try:\n        insert_rect = _insertion_rect(page, rect, resolved_font, target.size)"
assert marker in s
proto = '''    # ---- PROTOTYPE W1+W2+W3 (critique only) ----
    mode = os.environ.get("WIDEN_PROTO")
    horizontal = target.direction is None or (abs(target.direction[0] - 1) < 1e-6 and abs(target.direction[1]) < 1e-6)
    if mode and horizontal:
        from engine.widen_proto import right_limit
        origin = target.origin or (rect.x0, rect.y0 + target.size * resolved_font.ascender)
        if mode == "nowiden":
            R = rect.x1 + _WIDTH_PRECISION_PAD_PT
        else:
            R, _why = right_limit(page, tuple(rect), target.size)
            R = max(R, rect.x1) + _WIDTH_PRECISION_PAD_PT
        w_avail = R - origin[0]
        w_need = resolved_font.text_length(new_text, target.size)
        size = target.size if w_need <= w_avail else target.size * w_avail / w_need
        if size < target.size * _SHRINK_FLOOR_RATIO:
            raise RefusedBeforeMutation(
                f"text ({len(new_text)} chars) does not fit within the target region "
                f"{tuple(target.bbox)} even at the shrink floor ({target.size * _SHRINK_FLOOR_RATIO:.2f}pt, "
                f"50% of the original {target.size}pt); it would need {size:.2f}pt. Nothing was changed.")
        erase_rect = fitz.Rect(rect.x0, rect.y0, rect.x1 + _WIDTH_PRECISION_PAD_PT, rect.y1)
        _clean_erase(page, erase_rect)
        if resolved_fontname not in fitz.Base14_fontdict:
            page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)
        try:
            page.insert_text(fitz.Point(origin), new_text, fontname=resolved_fontname, fontsize=size, color=(0, 0, 0))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"failed to draw text at {origin} at {size:.2f}pt: {type(exc).__name__}: {exc}") from exc
        return

'''
s = s.replace(marker, proto + marker, 1)
open(p, "w").write(s)
print("worktree patched")
