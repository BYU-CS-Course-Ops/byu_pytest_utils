import inspect
from pathlib import Path
import pytest

pytest.register_assert_rewrite("byu_pytest_utils.io_checker")
pytest.register_assert_rewrite("byu_pytest_utils.dialog")

from .utils import run_python_script, with_import, ensure_missing  # nopep8
from .cpp_utils import compile_cpp, diff_outputs, format_results_for_gradescope  # nopep8
from .decorators import max_score, visibility, tags, cache, tier  # nopep8
from .dialog import run_script, run_exec

# Deprecated
from .dialog import dialog, dialog_exec  # nopep8

# Type stubs to make these variables discoverable
# Actual values are supplied by __getattr__
this_folder: Path
test_files: Path


def _get_caller_file() -> Path:
    s = inspect.stack()
    # Find the first frame outside the byu_pytest_utils package
    this_package_dir = Path(__file__).parent
    for frame in s:
        frame_path = Path(frame.filename)
        if not frame_path.is_relative_to(this_package_dir):
            return frame_path.absolute()
    # Fallback if all frames are in this package (shouldn't happen)
    return Path(__file__).absolute()

# We want `this_folder` to be the folder of the caller
def _get_caller_folder() -> Path:
    caller_file = _get_caller_file()
    return caller_file.parent


def __getattr__(name):
    if name == 'this_folder':
        return _get_caller_folder()
    elif name == 'test_files':
        return _get_caller_folder() / 'test_files'
    else:
        return globals()[name]
