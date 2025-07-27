from byu_pytest_utils import max_score

from byu_pytest_utils.test_sets import baseline, core, stretch1, stretch2

# BASELINE

@baseline
@max_score(10)
def test_basic_login():
    assert True

@baseline
@max_score(10)
def test_view_assignments():
    assert True

# CORE
@core
@max_score(10)
def test_dashboard_render():
    assert True


@stretch1
@max_score(10)
def test_toggle_dark_mode():
    assert False

@stretch1
@max_score(10)
def test_view_assignment_details():
    assert True

@stretch1
@max_score(10)
def test_submit_assignment():
    assert True


@stretch2
@max_score(10)
def test_animated_graphics():
    assert True
