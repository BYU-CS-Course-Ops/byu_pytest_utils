"""Tests for the empirical analysis helpers.

These are the first tests this module has had. They cover the two things a
student actually reads: the table of averaged runtimes, and the constant of
proportionality.

The case worth catching is fast code. An algorithm that finishes in
microseconds is measured in seconds by default, and three decimal places is
not enough to show it. A table of zeroes is indistinguishable from an
algorithm that does not scale, which is the opposite of what the exercise is
meant to teach.

Written as plain functions rather than classes on purpose: the pytest plugin
in this package raises a KeyError on any class-based test and takes the whole
session down with it.
"""
import builtins
import json

import pytest

from byu_pytest_utils.empirical_analysis_utils import (
    _plot_coefficients,
    compute_average_runtimes,
    compute_coefficient,
    format_runtime,
    print_markdown_table,
)


# compute_average_runtimes

def test_measurements_of_one_size_are_averaged():
    runtimes = [([10], 1.0), ([10], 2.0), ([10], 3.0)]
    assert compute_average_runtimes(runtimes) == [(10, 2.0)]


def test_each_size_is_averaged_separately():
    runtimes = [([10], 1.0), ([20], 4.0), ([10], 3.0), ([20], 6.0)]
    assert compute_average_runtimes(runtimes) == [(10, 2.0), (20, 5.0)]


def test_a_size_with_several_parameters_keeps_them_all():
    runtimes = [([10, 0.5], 1.0), ([10, 0.5], 3.0)]
    assert compute_average_runtimes(runtimes) == [(10, 0.5, 2.0)]


def test_a_microsecond_average_survives():
    """What used to be lost. Rounding to three decimals here threw the
    measurement away before anything could display it."""
    runtimes = [([100], 5.9e-05), ([100], 6.1e-05)]
    (_, average), = compute_average_runtimes(runtimes)
    assert average == pytest.approx(6.0e-05)


def test_input_order_does_not_decide_the_order_of_the_result():
    first = compute_average_runtimes([([10], 1.0), ([20], 2.0)])
    second = compute_average_runtimes([([20], 2.0), ([10], 1.0)])
    assert sorted(first) == sorted(second)


# format_runtime

def test_an_ordinary_runtime_keeps_three_decimals():
    assert format_runtime(19.63) == "19.630"


def test_a_microsecond_runtime_is_not_rendered_as_zero():
    assert format_runtime(5.9e-05) == "0.0000590"


def test_a_runtime_too_small_for_three_decimals_keeps_three_digits():
    assert format_runtime(0.000123456) == "0.000123"


def test_two_different_runtimes_do_not_render_the_same():
    """The quieter half of the bug. These both round to 0.001, so a column of
    them reads as an algorithm whose runtime stopped growing."""
    assert format_runtime(0.000610) != format_runtime(0.001292)
    assert format_runtime(0.000610) == "0.000610"
    assert format_runtime(0.001292) == "0.00129"


def test_a_genuine_zero_is_still_zero():
    assert format_runtime(0.0) == "0.000"


def test_an_input_size_is_left_alone():
    """Sizes share the row with runtimes and are not runtimes."""
    assert format_runtime(1600) == "1600"
    assert format_runtime("0.25") == "0.25"


# print_markdown_table

def test_the_table_shows_a_fast_runtime_rather_than_zero(capsys):
    print_markdown_table([(100, 5.9e-05)], ["Size", "Time (sec)"])
    printed = capsys.readouterr().out
    assert "0.0000590" in printed
    assert "| 0.000 " not in printed


def test_the_table_keeps_its_headers_and_rule(capsys):
    print_markdown_table([(100, 1.5)], ["Size", "Time (sec)"])
    lines = [l for l in capsys.readouterr().out.splitlines() if l.startswith("|")]
    assert lines[0] == "| Size | Time (sec) |"
    assert lines[1] == "| ---- | ---------- |"
    assert lines[2].startswith("| 100  | 1.500")


# compute_coefficient

@pytest.fixture
def no_window(monkeypatch):
    """Keep the chart off the screen without skipping the arithmetic."""
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)


def _runtimes_file(tmp_path, runtimes):
    path = tmp_path / "_runtimes.json"
    path.write_text(json.dumps(runtimes))
    return str(path)


def test_the_coefficient_is_returned_as_well_as_printed(tmp_path, capsys, no_window):
    """Without a return value nothing downstream can read the number, so it
    cannot be written into a results file or checked by a test."""
    filename = _runtimes_file(tmp_path, [[[10], 20.0], [[20], 40.0], [[30], 60.0]])
    coeff = compute_coefficient(filename, lambda n: n, None, None)
    assert coeff == pytest.approx(2.0)
    assert "2.0" in capsys.readouterr().out


def test_a_missing_matplotlib_names_the_install_command(monkeypatch):
    """matplotlib is an extra, so a student can reach this without it, and
    `No module named matplotlib` on its own does not say what to do."""
    real_import = builtins.__import__

    def without_matplotlib(name, *args, **kwargs):
        if name.split(".")[0] == "matplotlib":
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_matplotlib)

    with pytest.raises(ImportError, match="pip install matplotlib"):
        _plot_coefficients([1.0, 2.0], 1.5)


def test_start_and_end_select_measurements_not_sizes(tmp_path, no_window):
    """Recorded here because it reads as sizes and is not. The slice is over
    the flat list of measurements, so with several runs per size the index a
    student wants is a multiple of that count."""
    filename = _runtimes_file(
        tmp_path, [[[10], 100.0], [[10], 100.0], [[20], 40.0], [[20], 40.0]])
    assert compute_coefficient(filename, lambda n: n, 2, None) == pytest.approx(2.0)
