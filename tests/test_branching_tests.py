from byu_pytest_utils import max_score, tier
from byu_pytest_utils.popup.display import set_popup

set_popup(True)

baseline = tier('basic', 1)

core = tier('core', 2)

advanced = tier('advanced', 3)

stretch1 = tier('stretch1', 4)

stretch2 = tier('stretch2', 5)


@baseline
@max_score(10)
def test_basic_login():
    assert True


@baseline
@max_score(10)
def test_view_assignments():
    assert True


@core
@max_score(10)
def test_dashboard_render():
    assert True


@advanced
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
