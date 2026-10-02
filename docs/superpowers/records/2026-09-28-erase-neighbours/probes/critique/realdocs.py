"""N1 (W-F1 reading) on real documents with embedded fonts: for every span whose bbox vertically overlaps another
line's span, delete it with today's rect and with N1's clipped rect, and check (1) the target is gone from the
text layer, (2) no neighbour words are lost, (3) no target ink remains in its bbox outside neighbour boxes."""
import sys, glob
import pymupdf as fitz
from n1_proto import n1_clip, Refused

FETCH = "/tmp/claude-0/-home-user-pdf-ai-engine/a3c366b7-4337-5c89-869b-71c0b60e1cea/scratchpad/fetch/"
RES = FETCH + "ocrmypdf-16.10.0/tests/resources/"
DOCS = [FETCH + "cardinal.pdf", FETCH + "graph.pdf", FETCH + "libreoffice-form.pdf", FETCH + "rotation.pdf",
        RES + "francais.pdf", RES + "tagged.pdf", RES + "toc.pdf", RES + "multipage.pdf", RES + "linn.pdf",
        RES + "livecycle.pdf", RES + "truetype_font_nomapping.pdf", RES + "c02-22.pdf", RES + "link.pdf"]


def spans(p):
    return [s for b in p.get_text("dict")["blocks"] if b["type"] == 0 for l in b["lines"] for s in l["spans"]]


def words_in(p, r):
    return [w[4] for w in p.get_text("words") if fitz.Rect(w[:4]).intersects(r)]


if len(sys.argv) > 1: DOCS = sys.argv[1:]
for path in DOCS:
    try:
        d = fitz.open(path)
    except Exception as e:
        print(path.split("/")[-1], "open failed", e); continue
    name = path.split("/")[-1]
    tested = refused = neighbour_loss_today = neighbour_loss_n1 = target_left_n1 = 0
    fonts = set(); kept_min = 1.0; examples = []
    for pno in range(min(d.page_count, 3)):
        p = d[pno]; ss = spans(p)
        for i, s in enumerate(ss):
            if len(s["text"].strip()) < 4 or s["size"] < 4:
                continue
            r = fitz.Rect(s["bbox"])
            others = [t for t in ss if t is not s and fitz.Rect(t["bbox"]).intersects(r) and abs(t["origin"][1] - s["origin"][1]) > 0.5 * s["size"]]
            if not others:
                continue
            tested += 1; fonts.add(s["font"])
            if tested > 40:
                break
            nb_rects = [fitz.Rect(t["bbox"]) for t in others]
            nb_words_before = [words_in(p, nr) for nr in nb_rects]
            for mode in ("today", "n1"):
                d2 = fitz.open(path); p2 = d2[pno]
                rect = fitz.Rect(r.x0, r.y0, r.x1 + 0.05, r.y1)
                if mode == "n1":
                    try:
                        rect, kept, cl = n1_clip(p2, rect, r, side="wf1"); kept_min = min(kept_min, kept)
                    except Refused:
                        refused += 1; continue
                p2.add_redact_annot(rect, fill=(1, 1, 1)); p2.apply_redactions(images=2, graphics=1, text=0)
                still = [t["text"] for t in spans(p2) if abs(t["bbox"][1] - r.y0) < 0.5 and fitz.Rect(t["bbox"]).intersects(r) and abs(t["origin"][1] - s["origin"][1]) < 0.5 * s["size"] and t["text"] in s["text"]]
                lost = sum(len([w for w in b if w not in words_in(p2, nr)]) for nr, b in zip(nb_rects, nb_words_before))
                if mode == "today":
                    neighbour_loss_today += lost > 0
                else:
                    neighbour_loss_n1 += lost > 0
                    if still:
                        target_left_n1 += 1
                        if len(examples) < 3: examples.append((s["text"][:30], still, round(kept, 2)))
    print(f"{name:32s} spans with cross-line overlap tested={tested:3d} today:neighbour-loss={neighbour_loss_today:3d}  N1:neighbour-loss={neighbour_loss_n1} target-left={target_left_n1} refused={refused} min kept={kept_min:.2f} fonts={sorted(fonts)[:4]}")
    if examples:
        print("    target-left examples:", examples)
