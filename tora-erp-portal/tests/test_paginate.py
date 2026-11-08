import sys

sys.path.append("slapz102_core")
sys.path.append("slapz102_modules")
sys.path.append("slapz102_settings")
sys.path.append("slapz102_stdlib")
sys.path.append("slapz102_storage")

from slapz102_stdlib import paginate

def test_read_params_defaults_and_whitelist():
    assert paginate.read_params({}) == (1, paginate.DEFAULT_PAGE_SIZE)
    assert paginate.read_params({"page": "3", "per_page": "20"}) == (3, 20)
    assert paginate.read_params({"page": "-5", "per_page": "999999"}) == (1, paginate.DEFAULT_PAGE_SIZE)
    assert paginate.read_params({"page": "abc", "per_page": "x"}) == (1, paginate.DEFAULT_PAGE_SIZE)
# end def

def test_build_middle_page():
    pager = paginate.build(213, 2, 80)
    assert pager["pages"] == 3
    assert pager["offset"] == 80
    assert pager["start"] == 81
    assert pager["end"] == 160
    assert pager["has_prev"] == True
    assert pager["has_next"] == True
# end def

def test_build_clamps_out_of_range_page():
    pager = paginate.build(213, 99, 80)
    assert pager["page"] == 3
    assert pager["start"] == 161
    assert pager["end"] == 213
    assert pager["has_next"] == False
# end def

def test_build_empty():
    pager = paginate.build(0, 1, 80)
    assert pager["pages"] == 1
    assert pager["start"] == 0
    assert pager["end"] == 0
    assert pager["window"] == [1]
# end def

def test_window_has_gaps():
    pager = paginate.build(2000, 10, 20)
    assert pager["window"] == [1, None, 8, 9, 10, 11, 12, None, 100]
# end def
