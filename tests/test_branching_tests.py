from byu_pytest_utils import max_score

from test_sets import baseline, core, advanced, stretch1, stretch2

@max_score(10)
def test_basic_login():
    assert True

@max_score(10)
def test_view_assignments():
    assert True

@max_score(10)
def test_dashboard_render():
    assert True

@max_score(10)
def test_toggle_dark_mode():
    assert False

@max_score(10)
def test_view_assignment_details():
    assert True

@max_score(10)
def test_submit_assignment():
    assert True

@max_score(10)
def test_animated_graphics():
    assert True
