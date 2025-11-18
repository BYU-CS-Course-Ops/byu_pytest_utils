from byu_pytest_utils import dialog, max_score, test_files, tier

baseline = tier('basic', 1)

core = tier('core', 2)

advanced = tier('advanced', 3)

stretch1 = tier('stretch1', 4)

stretch2 = tier('stretch2', 5)

@baseline
@dialog(
    "test_files/test_dialog_should_pass.txt",
    "script_for_dialog_passes.py", 'woot', 7
)
@max_score(10)
def test_dialog_should_pass():
    """Everything should pass"""

@core
@dialog(
    "test_files/test_dialog_should_pass.txt",
    "script_for_dialog_fails.py", 'woot', 7, 'foobar'
)
@max_score(10)
def test_dialog_should_fail():
    """
    seven should pass, but another-number and everything-else should fail
    """

@advanced
@dialog(
    "test_files/test_dialog_expects_more_input.txt",
    "script_for_dialog_passes.py", 'woot'
)
@max_score(10)
def test_dialog_expects_more_input_should_fail():
    """
    args, seven, and eight should pass,
    but nine and everything-else should not
    """

@stretch1
@max_score(10)
@dialog(
    "test_files/test_dialog_expects_less_input.txt",
    "script_for_dialog_passes.py", 'woot'
)
def test_dialog_expects_less_input_should_fail():
    """
    seven should pass, but everything-else should fail
    There should be an error: "Input called more times than expected"
    """

@stretch2
@max_score(10)
@dialog(
    "test_files/basic_text_output.expected.txt",
    "script_that_writes_to_file.py",
    test_files / "basic_text_input_file.txt",
    "basic_text_output.observed.txt",
    output_file="basic_text_output.observed.txt"
)
def test_dialog_output_file():
    """
    Should pass cleanly
    """

@stretch2
@max_score(10)
@dialog(
    "test_files/basic_text_output.dialog.expected.txt",
    "script_that_writes_to_file.py",
    test_files / "basic_text_input_file.txt",
    "basic_text_output.observed.txt",
    output_file="basic_text_output.observed.txt"
)
def test_dialog_output_file_groups():
    """
    Should match with partial-credit groups
    """
