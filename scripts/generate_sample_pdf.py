"""One-time generator for the demo's bundled sample document. Run manually:
    ./.venv/Scripts/python.exe scripts/generate_sample_pdf.py

Produces webui/static/sample-document.pdf -- a realistic-looking (entirely
fictional) patient intake form, bundled so the webui's "Try a sample
document" button has something to load instantly, without a visitor needing
to find and upload their own PDF first. Not run at request time or as part
of the test suite -- the output is checked into git, same reasoning as
tests/fixtures/generate_fixtures.py.

Every name, number, and address below is invented for this demo. Deliberate
touches: a Social Security Number, phone numbers, and a home address as
realistic redaction targets, plus one intentional typo ("Aprill 12") as a
target for a replace-style instruction ("fix the typo in the next
appointment date").
"""
import pymupdf as fitz
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent.parent / "webui" / "static" / "sample-document.pdf"

INK = (0.180, 0.204, 0.251)  # Nord --ink, #2e3440
ACCENT = (0.369, 0.506, 0.675)  # Nord --accent, #5e81ac


def make_sample_document() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    left = 72
    top = 90

    page.insert_text(
        (left, top),
        "Sunrise Family Clinic",
        fontsize=20,
        fontname="Helvetica-Bold",
        color=INK,
    )
    page.insert_text(
        (left, top + 22),
        "Patient Intake Form",
        fontsize=13,
        fontname="Helvetica",
        color=ACCENT,
    )
    page.draw_line((left, top + 36), (612 - left, top + 36), color=ACCENT, width=1.2)

    fields = [
        "Patient Name: Jordan A. Whitfield",
        "Date of Birth: 03/14/1985",
        "Social Security Number: 512-34-9081",
        "Home Address: 4821 Larkspur Lane, Meridian, ID 83642",
        "Phone Number: (208) 555-0173",
        "Emergency Contact: Dana Whitfield -- (208) 555-0199",
        "Reason for Visit: Follow-up for hypertension management.",
        "Physician Notes: Blood pressure 148/92. Continue Lisinopril 10mg. Follow-up in 4 weeks.",
        "Next Appointment: Aprill 12, 2026",
    ]

    y = top + 76
    line_height = 30
    for field in fields:
        page.insert_text((left, y), field, fontsize=12, fontname="Helvetica", color=INK)
        y += line_height

    doc.save(OUTPUT_PATH)
    doc.close()
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    make_sample_document()
