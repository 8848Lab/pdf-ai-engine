

OVERHANG_CASES = {
    "left": ("[-40 0 612 792]", True),
    "top": ("[0 0 612 830]", True),
    "all-four": ("[-40 -60 660 820]", True),
    "bottom": ("[0 -60 612 792]", False),
    "right": ("[0 0 660 792]", False),
    "contained": ("[40 60 580 740]", False),
}
TEXT_OPS = {
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, -100)),
    "insert_block": lambda h, b: insert_block(h, 0, (72, 300, 400, 320), "NEW", 12.0),
}
OTHER_OPS = {
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
    "delete_block": lambda h, b: delete_block(h, 0, b),
}


@pytest.mark.parametrize("case", sorted(OVERHANG_CASES))
@pytest.mark.parametrize("op", sorted(TEXT_OPS))
def test_text_operations_refuse_exactly_the_overhang_pages(op, case):
    cropbox, refused = OVERHANG_CASES[case]
    doc, handle = parse(build_page(cropbox=cropbox))
    before = fingerprint(handle)
    if refused:
        with pytest.raises(ValueError, match="CropBox"):
            TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))
        assert fingerprint(handle) == before
    else:
        TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))  # no false positive


@pytest.mark.parametrize("op", sorted(OTHER_OPS))
def test_redaction_and_erasing_still_work_on_an_overhang_page(op):
    doc, handle = parse(build_page(cropbox=OVERHANG_CASES["all-four"][0]))
    OTHER_OPS[op](handle, block(doc, "LOW-MARKER"))
    assert "LOW-MARKER" not in exported(handle)[0].get_text()


def test_text_operations_are_allowed_on_a_negative_origin_mediabox():
    # Regression guard: mediabox.contains(cropbox) would refuse this page,
    # which draws correctly.
    doc, handle = parse(build_page(mediabox="[-100 -100 512 692]"))
    replace_text(handle, 0, block(doc, "LOW-MARKER"), "LOW-MARKER")  # must not raise


ALL_TARGETED = {**TEXT_OPS, **OTHER_OPS}


# 0.5 as well as 1.5: a gate written as "unit > 1" passes every 1.5 case.
@pytest.mark.parametrize("unit", (0.5, 1.5))
@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_user_unit_page_with_the_owners_warning(op, unit):
    doc, handle = parse(build_page(user_unit=unit))
    before = fingerprint(handle)
    with pytest.raises(ValueError) as caught:
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    message = str(caught.value)
    assert "/UserUnit" in message
    assert "nothing was changed" in message
    assert "Support is planned" in message
    assert fingerprint(handle) == before


@pytest.mark.parametrize("unit", (0.5, 1.5))
def test_replace_image_refuses_a_user_unit_page(unit):
    doc, handle = parse(build_page(user_unit=unit, image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Support is planned"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_malformed_rotation(op):
    # P3, with the gate's own message: the marker sits on the page, so the
    # bbox check passes and only the gate can refuse.
    doc, handle = parse(build_page(rotate_raw="45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    assert fingerprint(handle) == before


def test_replace_image_refuses_a_malformed_rotation():
    doc, handle = parse(build_page(rotate_raw="45", image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


def test_an_inherited_malformed_rotation_is_refused():
    # /Rotate 45 set only on the /Pages parent reaches the gate through the
    # Task 2 reader's /Parent walk.
    doc, handle = parse(_inherited_rotation_page("45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert fingerprint(handle) == before


def test_move_block_refuses_when_the_source_page_uses_user_unit():
    # P4: the source is erased, and an erase paints a fill.
    doc, handle = parse(build_page(user_unit=1.5, extra_pages=1))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 0 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 100))
    assert fingerprint(handle) == before


def _plain_page_then_user_unit_page():
    source = fitz.open(stream=build_page(extra_pages=1), filetype="pdf")
    source[1].insert_text((72, 100), "PAGE-ONE", fontsize=12)
    source.xref_set_key(source[1].xref, "UserUnit", "1.5")
    data = source.tobytes()
    source.close()
    return data


def test_move_block_refuses_an_unsupported_destination_page_and_keeps_the_source():
    # P4, the other direction: a plain source page moving onto a /UserUnit
    # page. The destination gate must fire before the source is erased.
    doc, handle = parse(_plain_page_then_user_unit_page())
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 300))
    assert fingerprint(handle) == before
    assert "LOW-MARKER" in exported(handle)[0].get_text()


def test_gate_uses_the_target_pages_own_geometry():
    # Review Focus 1: page 1 uses /UserUnit, page 0 is plain. Page 0 must
    # stay fully editable, and page 1 must be refused.
    doc, handle = parse(_plain_page_then_user_unit_page())
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)  # page 0: allowed
    page_one = next(b for b in doc.pages[1].text_blocks if "PAGE-ONE" in b.text)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        redact_region(handle, 1, page_one.bbox)
