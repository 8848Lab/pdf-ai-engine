import sys
sys.path.insert(0, "C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t2")
from adversarial import *  # noqa

LETTER = "/MediaBox [0 0 612 792]"

print("### raw key text seen by the gate for large integers")
for key, val in (("UserUnit", "4294967297"), ("UserUnit", "8589934593"), ("UserUnit", "-4294967295"),
                 ("UserUnit", "4294967298"), ("Rotate", "4294967341"), ("Rotate", "2700000000.0"),
                 ("Rotate", "4294967040.0"), ("Rotate", "2700000000"), ("UserUnit", "1e0"), ("Rotate", "9e1")):
    doc = fitz.open(stream=standard(f"{LETTER} /{key} {val}"), filetype="pdf")
    page = doc[0]
    print(f"  /{key} {val:<16} -> xref_get_key={doc.xref_get_key(page.xref, key)!r}  page.rect={page.rect} rotation={page.rotation}")
    doc.close()

for key, val in (("UserUnit", "4294967297"), ("UserUnit", "8589934593"), ("UserUnit", "-4294967295"),
                 ("Rotate", "4294967341"), ("Rotate", "2700000000.0"), ("Rotate", "4294967040.0")):
    report(f"M. /{key} {val}", standard(f"{LETTER} /{key} {val}"))

# indirect huge UserUnit
report("M2. /UserUnit -> obj4 = 4294967297", standard(f"{LETTER} /UserUnit 4 0 R", extra_objects=["4294967297"]))

# 3-entry CropBox variants to characterise MuPDF's zero-fill
report("N1. CropBox [10 10 600] (3 entries, contained-ish)", standard(f"{LETTER} /CropBox [10 10 600]"))
report("N2. CropBox [0 0 612 792 -40] (5th entry ignored?)", standard(f"{LETTER} /CropBox [0 0 612 792 -40]"))
report("N3. MediaBox [4 0 R 0 612 792] obj4=0 + CropBox [-40 0 612 792]",
       standard("/MediaBox [4 0 R 0 612 792] /CropBox [-40 0 612 792]", extra_objects=["0"]))
