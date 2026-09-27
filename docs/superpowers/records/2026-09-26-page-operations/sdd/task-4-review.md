# Task 4 review: background sampling (D2, R3), f03efe7..9de0ae3

## Spec compliance: ✅

- `engine/operations.py:15` adds `to_display_matrix` next to `unrotated_bounds`. That follows ruling S1: only the names this task uses are imported.
- `engine/operations.py:235-258` replaces both parts of `_sample_background_color` exactly as the brief's Step 3 specifies: the display-matrix mapping, subtraction of the pixmap origin, and the same clamp. The signature `(page, rect) -> tuple[float, float, float]` is unchanged.
- `tests/test_page_geometry.py:195-253` appends the brief's Step 1 block verbatim: `_centre_pixel`, `BAND_BEHIND_LOW`, `SAMPLE_CROPS` and the three tests.
- Scope: `git diff --stat` shows only `engine/operations.py` and `tests/test_page_geometry.py`. No pre-Merge-A test was edited, and neither was `tests/test_geometry.py`.
- The end-to-end assertion in `test_delete_block_erases_to_the_true_background_colour` reads `exported(handle)[0]`, so it checks re-parsed bytes. The other two tests call the sampler directly, which is how the brief designed them (C3 isolation).
- Missing, Extra or Misunderstood items: none.

## Code quality: Approved

No Critical, Important or Minor findings.

### Named risk 1: the clamp on a cropped page

The clamp never reads a pixel outside the visible area. `page.get_pixmap()` renders `page.rect`, which is exactly the visible (CropBox) area in display space. I measured `pixmap.x == pixmap.y == 0`, with a size equal to `page.rect` at all four rotations on the contained crop. So every clamped index is a real visible pixel.

What the clamp does is substitute the nearest visible pixel in the same display row or column for an off-canvas sample point. There are two cases:

- **The rect is on the page.** A sample can fall off-canvas only by up to the 3pt offset. The clamped pixel is then at most 3pt from the requested spot, on the visible edge. That is acceptable.
- **The rect straddles the visible edge.** `_validate_target` accepts any rect that intersects the page. The clamped pixel can then land inside the rect and read a glyph stroke. The median of four samples mitigates this.

This behaviour predates the change: the old code clamped identically, and Task 4 did not introduce or widen it. It is not a Task 4 finding. If anyone wants it addressed, it belongs in the final review as a separate item ("drop off-canvas samples and take the median of the rest"). It is not a fix for this task.

### Named risk 2: rotation 0 on integer pages is unchanged

I confirmed this by reading the code and running a direct probe, not the test suite:

- `to_display_matrix` at rotation 0 is `Matrix(0) * translate(-0, -0)`, which is the identity. On a 612x792 page it measured `Matrix(1, 0, 0, 1, 0, 0)`, and `Matrix(0) == fitz.Identity` is True.
- The pixmap irect is `(0, 0, 612, 792)`, so `pixmap.x` and `pixmap.y` are 0.
- The new index is therefore `int(x_pt)`. The old index was `int(x_pt * (612/612))`, and `612/612` is exactly 1.0, so it was also `int(x_pt)`. The two are bit-identical, and the same holds for y.
- This also holds at rotation 0 with a CropBox of integer size, because `page.rect` stays `(0, 0, w, h)`.

## Checks run

- I read the brief, the report and the diff, and I read `engine/geometry.py` (`to_display_matrix`, `unrotated_bounds`) and `_validate_target`.
- `git diff --stat f03efe7 9de0ae3` confirmed the diff touches only the two permitted files.
- A throwaway probe script in the scratchpad checked the following:
  - `Matrix(0)` equals the identity.
  - `to_display_matrix` is the identity on a 612x792 page at rotation 0, and the pixmap irect there is `(0, 0, 612, 792)`.
  - On the contained crop `[40 60 580 740]`, the pixmap origin is (0, 0) at all four rotations and its size equals `page.rect`.
  - An off-canvas unrotated point maps to display coordinates just outside the pixmap. The clamp therefore pulls the read onto the visible edge.
- I ran no test suite, and I did not re-run the implementer's mutation checks.
