"""Tests for the plugin's bookkeeping of test results.

The plugin files every test's score under a key, then looks that key up twice:
once to attach the tier, and once to build the report. A key that is written
one way and read another is not a wrong number in a report, it is a KeyError
during collection that takes the whole session down before a single test runs.
So these check the shapes a test can take: inside a class, parametrized, and
tiered alongside untiered ones.

Each session runs in a subprocess, for two reasons. The plugin keeps its
registry in module-level state that the session we are already inside has
filled. And a session that dies takes its own report with it, so a regression
here has to be observed from outside to be reported as a failure.
"""
import json
import os
import subprocess
import sys

# Imported as the module, since pytest tries to collect anything named Test*.
from byu_pytest_utils.html_comparison import models
from byu_pytest_utils.html_comparison.renderers import TieredTestRenderer


def run_pytest(tmp_path, source: str, gradescope: bool = False):
    """Run one pytest session over `source` in a directory of its own."""
    (tmp_path / "test_generated.py").write_text(source)

    env = dict(os.environ)
    if gradescope:
        env["GRADESCOPE"] = "1"
    else:
        env.pop("GRADESCOPE", None)

    return subprocess.run(
        [sys.executable, "-m", "pytest", "test_generated.py", "-q", "-p", "no:randomly"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
    )


def scores(tmp_path, source: str) -> dict:
    """The score each test earned, as the autograder would record it."""
    result = run_pytest(tmp_path, source, gradescope=True)
    assert_session_survived(result)

    graded = json.loads((tmp_path / "results.json").read_text())
    return {t["name"]: (t["score"], t["max_score"]) for t in graded["tests"]}


def assert_session_survived(result):
    output = result.stdout + result.stderr
    assert "INTERNALERROR" not in output, output
    assert result.returncode == 0, output


def test_a_test_inside_a_class_runs(tmp_path):
    assert_session_survived(run_pytest(
        tmp_path,
        "class TestGrouped:\n"
        "    def test_in_a_class(self):\n"
        "        assert True\n",
    ))


def test_a_parametrized_test_runs(tmp_path):
    assert_session_survived(run_pytest(
        tmp_path,
        "import pytest\n"
        "\n"
        "@pytest.mark.parametrize('n', [1, 2])\n"
        "def test_parametrized(n):\n"
        "    assert n\n",
    ))


def test_a_parametrized_test_inside_a_class_runs(tmp_path):
    assert_session_survived(run_pytest(
        tmp_path,
        "import pytest\n"
        "\n"
        "class TestGrouped:\n"
        "    @pytest.mark.parametrize('n', [1, 2])\n"
        "    def test_parametrized(self, n):\n"
        "        assert n\n",
    ))


def test_a_tiered_run_still_works(tmp_path):
    """The ordinary case, so the fix for the others cannot quietly break it."""
    assert_session_survived(run_pytest(
        tmp_path,
        "from byu_pytest_utils import max_score, tier\n"
        "\n"
        "@tier('basic', 1)\n"
        "@max_score(10)\n"
        "def test_first():\n"
        "    assert True\n",
    ))


def test_a_tiered_and_an_untiered_test_in_one_run(tmp_path):
    """Running a directory mixes files, and an untiered test has no priority
    to sort by. Sorting it against a tiered one raised a TypeError."""
    result = run_pytest(
        tmp_path,
        "from byu_pytest_utils import max_score, tier\n"
        "\n"
        "@tier('basic', 1)\n"
        "@max_score(10)\n"
        "def test_tiered():\n"
        "    assert True\n"
        "\n"
        "def test_untiered():\n"
        "    assert True\n",
    )

    assert "TypeError" not in result.stdout + result.stderr
    assert_session_survived(result)


def test_a_test_inside_a_class_is_worth_its_declared_score(tmp_path):
    """The quiet half. A test filed under a key nobody looks up is graded out
    of nothing, which is a passing student with a zero rather than a crash."""
    earned = scores(
        tmp_path,
        "from byu_pytest_utils import max_score\n"
        "\n"
        "class TestGrouped:\n"
        "    @max_score(10)\n"
        "    def test_in_a_class(self):\n"
        "        assert True\n",
    )

    assert earned == {"TestGrouped::test_in_a_class": (10, 10)}


def test_a_parametrized_test_is_worth_its_declared_score(tmp_path):
    earned = scores(
        tmp_path,
        "import pytest\n"
        "\n"
        "from byu_pytest_utils import max_score\n"
        "\n"
        "@pytest.mark.parametrize('n', [1, 2])\n"
        "@max_score(10)\n"
        "def test_parametrized(n):\n"
        "    assert n\n",
    )

    assert earned == {"test_parametrized": (10, 10)}


def test_a_tiered_run_is_graded_as_tiered_whichever_test_comes_first(tmp_path):
    """The grading side used to ask only the first result whether the run was
    tiered, while the HTML report asked all of them. Disagreeing cost a test
    its line in the autograder output."""
    earned = scores(
        tmp_path,
        "from byu_pytest_utils import max_score, tier\n"
        "\n"
        "def test_untiered_and_first():\n"
        "    assert True\n"
        "\n"
        "@tier('basic', 1)\n"
        "@max_score(10)\n"
        "def test_tiered():\n"
        "    assert True\n",
    )

    assert "basic" in earned


def _result(name, tier=None, priority=None, passed=True):
    return models.TestResults(
        test_name=name,
        test_tier=tier,
        test_priority=priority,
        score=1 if passed else 0,
        max_score=1,
        observed="",
        expected="",
        passed=passed,
    )


def test_tiers_are_ordered_by_priority():
    order = TieredTestRenderer.get_tier_order(
        [_result("c", "advanced", 3), _result("a", "basic", 1), _result("b", "core", 2)]
    )
    assert order == ["basic", "core", "advanced"]


def test_an_untiered_test_sorts_last():
    """Not merely somewhere: a failure in the first tier marks every tier
    behind it as skipped, so an untiered test at the front would hide them."""
    order = TieredTestRenderer.get_tier_order(
        [_result("loose"), _result("a", "basic", 1), _result("b", "core", 2)]
    )
    assert order == ["basic", "core", None]
