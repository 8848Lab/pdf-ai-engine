

from engine.geometry import to_display_matrix  # noqa: E402
from engine.operations import _sample_background_color  # noqa: E402
from tests.geometry_helpers import BAND, BAND_RGB  # noqa: E402

BAND_BEHIND_LOW = (60, 680, 400, 720)
SAMPLE_CROPS = {"plain": None, "contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _centre_pixel(page, bbox):
    pix = page.get_pixmap()
    c = fitz.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2) * to_display_matrix(page)
    return tuple(pix.pixel(int(c.x - pix.x), int(c.y - pix.y))[:3])


@pytest.mark.parametrize("crop", sorted(SAMPLE_CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_background_sample_reads_the_colour_behind_the_block(rotation, crop):
    # D2, tested on the sampler itself (C3). Through an erase, a contained or
    # oversized crop would also move the fill (R11, Task 5), and the old fill
    # landing elsewhere leaves the original band showing at the checked spot
    # -- a false green. Sampling alone is isolated here.
    doc, handle = parse(build_page(rotation=rotation, cropbox=SAMPLE_CROPS[crop], band=BAND_BEHIND_LOW))
    rect = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    rgb = tuple(round(c * 255) for c in _sample_background_color(handle[0], rect))
    assert rgb == BAND_RGB


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_delete_block_erases_to_the_true_background_colour(rotation):
    # End to end on a plain page only: with no CropBox the fill already lands
    # on target (R11 needs a crop), so a wrong colour here is sampling alone.
    doc, handle = parse(build_page(rotation=rotation, band=BAND_BEHIND_LOW))
    b = block(doc, "LOW-MARKER")
    delete_block(handle, 0, b)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    r, g, bl = _centre_pixel(page, b.bbox)
    assert bl > 240 and r < 200, f"erased area is {(r, g, bl)}, expected the band {BAND_RGB}"


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_sampling_is_exact_on_a_fractional_size_page(rotation):
    # R3: a 100.1 x 800.1 page renders 101 x 801 pixels, so inferring scale
    # from raster size (1.008991) lands samples on the wrong pixels; the old
    # sampler also never rotates its points (D2), so every rotation fails.
    # The four sample points of rect (40, 700, 60, 720) are (50, 697),
    # (50, 723), (37, 710) and (63, 710). Each is the centre of a 2x2 band
    # patch, so under the identity render it falls on a pixel INSIDE the
    # patch; a sample that misses by a few pixels reads white.
    doc = fitz.open()
    page = doc.new_page(width=100.1, height=800.1)
    for x, y in ((50, 697), (50, 723), (37, 710), (63, 710)):
        page.draw_rect(fitz.Rect(x - 1, y - 1, x + 1, y + 1), color=None, fill=BAND)
    page.set_rotation(rotation)
    rgb = tuple(round(c * 255) for c in _sample_background_color(page, fitz.Rect(40, 700, 60, 720)))
    assert rgb == BAND_RGB
    doc.close()
