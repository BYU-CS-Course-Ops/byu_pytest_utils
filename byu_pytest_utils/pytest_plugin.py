import os
import re
import json
import pytest
import webbrowser
import tempfile
import sys

from byu_pytest_utils.utils import quote
from byu_pytest_utils.html_comparison import (
    TestResults, HTMLRenderer,
    get_comparison_results, format_gradescope_results,
    get_css, inline_css
)

metadata = {}
test_group_stats = {}
html_result_path = None

MIN_LINES_DIFF = 3


def pytest_configure(config):
    config.addinivalue_line("markers", "tier: mark a test as part of a specific tier")


def pytest_assertrepr_compare(config, op, left, right):
    if op == '==' \
            and isinstance(left, str) and len(left_lines := left.splitlines()) > MIN_LINES_DIFF \
            and isinstance(right, str) and len(right_lines := right.splitlines()) > MIN_LINES_DIFF:
        # Use custom side-by-side assertion diff
        # How wide?
        left_width = max((len(line) for line in left_lines))
        right_width = max((len(line) for line in right_lines))
        left_view_lines = [f"{line:<{left_width}}" for line in left_lines]
        right_view_lines = [f"{line:<{right_width}}" for line in right_lines]

        # Pad with empty lines
        while len(left_view_lines) < len(right_view_lines):
            left_view_lines.append(' ' * left_width)
        while len(right_view_lines) < len(left_view_lines):
            right_view_lines.append(' ' * right_width)

        # Join lines side by side
        diff_view = [
            'Observed (left) == Expected (right)',
            *(l + ' | ' + r for l, r in zip(left_view_lines, right_view_lines))
        ]
        return diff_view


def _stats_key(nodeid):
    """The key a test's stats are filed under: its node id without directories."""
    return nodeid.split('/')[-1]


def _stats_for(nodeid):
    """The stats for one collected test, copied from its function's if absent.

    A test parametrized by pytest itself is filed before its parameter ids
    exist, so each of its cases is first seen here under a key of its own.
    """
    key = _stats_key(nodeid)

    if key not in test_group_stats:
        base = re.sub(r'\[.*]$', '', key)
        test_group_stats[key] = dict(test_group_stats.get(base, {'max_score': 0}))

    return test_group_stats[key]


def pytest_generate_tests(metafunc):
    # The node id, not the module and function names: a test inside a class is
    # named for its class as well, and is filed under a key nothing looks up.
    test_name = _stats_key(metafunc.definition.nodeid)

    if hasattr(metafunc.function, '_group_stats'):
        group_stats = metafunc.function._group_stats

        for group_name, stats in group_stats.items():
            stats['max_score'] *= getattr(metafunc.function, 'max_score', 0)
            stats['score'] *= getattr(metafunc.function, 'max_score', 0)
            test_group_stats[f'{test_name}[{group_name}]'] = stats

        metafunc.parametrize('group_name', group_stats.keys())
    else:
        test_group_stats[test_name] = {
            'max_score': getattr(metafunc.function, 'max_score', 0)
        }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item):
    x = yield
    if item._obj not in metadata:
        metadata[item._obj] = {}
    metadata[item._obj]['max_score'] = getattr(item._obj, 'max_score', 0)
    metadata[item._obj]['visibility'] = getattr(
        item._obj, 'visibility', 'visible')
    x._result.metadata_key = item._obj


@pytest.hookimpl(hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    # Deprecated function - remove with CheckIO stuff
    outcome = yield
    excinfo = outcome.excinfo
    if excinfo is not None \
            and excinfo[0] is AssertionError \
            and hasattr(excinfo[1], '_partial_credit'):
        metadata[pyfuncitem._obj]['partial_credit'] = excinfo[1]._partial_credit


def pytest_collection_modifyitems(items):
    for item in items:
        test_tier, test_priority = None, None

        if marker := item.get_closest_marker('tier'):
            test_tier = marker.kwargs.get('tier_name')
            test_priority = marker.kwargs.get('tier_priority')

        _stats_for(item.nodeid).update({
            'test_tier': test_tier,
            'test_priority': test_priority,
        })


def parse_info(all_tests):
    """
    Convert test result dictionary into a list of ComparisonInfo.
    """
    comparison_info = []
    for s in all_tests:
        # Everything after the file, so a test in a class keeps its class.
        test_case_name = re.sub(r'\[.*]$', '', '::'.join(s.nodeid.split('::')[1:]))

        group_stats = _stats_for(s.nodeid)

        test_tier = group_stats.get('test_tier')
        test_priority = group_stats.get('test_priority')
        max_score = group_stats['max_score']
        score = group_stats.get('score', max_score if s.passed else 0)

        comparison_info.append(
            TestResults(
                test_name=test_case_name,
                test_tier=test_tier,
                test_priority=test_priority,
                score=round(score, 4),
                max_score=round(max_score, 4),
                observed=group_stats.get('observed', ''),
                expected=group_stats.get('expected', ''),
                output=s.longreprtext,
                passed=s.passed
            )
        )

    return comparison_info


def pytest_sessionfinish(session, exitstatus):
    """
    Hook to render the HTML file after all tests are finished.
    """
    if session.config.getoption("--collect-only"):
        # VS Code runs --collect-only on every file save to enumerate the
        # unit tests so that it can list them in the UI. No results.
        return

    terminalreporter = session.config.pluginmanager.getplugin('terminalreporter')

    all_tests = []
    if 'passed' in terminalreporter.stats:
        all_tests += terminalreporter.stats['passed']
    if 'failed' in terminalreporter.stats:
        all_tests += terminalreporter.stats['failed']

    test_file_name = session.config.args[0].split('/')[-1].split('.')[0]

    test_results = parse_info(all_tests)

    renderer = HTMLRenderer()
    html_content = renderer.render(
        test_file_name=test_file_name,
        test_results=test_results,
    )

    from byu_pytest_utils.popup import get_popup
    popup = get_popup()
    gradescope = os.getenv('GRADESCOPE')

    if gradescope:
        html_results = get_comparison_results(html_content=html_content)
        gradescope_output = format_gradescope_results(test_results, html_results)
        results = inline_css(gradescope_output, get_css())

        with open('results.json', 'w') as f:
            json.dump(results, f, indent=2)
    else:
        # Always create the HTML results file in a persistent temporary directory
        temp_dir = os.path.join(tempfile.gettempdir(), 'pytest_results')
        os.makedirs(temp_dir, exist_ok=True)

        result_path = os.path.join(temp_dir, f'{test_file_name}_results.html')
        with open(result_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Store result_path for use in pytest_terminal_summary
        global html_result_path
        html_result_path = result_path

        if popup:
            webbrowser.open(f'file://{quote(result_path)}')


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Hook to add HTML results link at the very end of terminal output.
    """
    global html_result_path

    if html_result_path:
        # Add clickable hyperlink to terminal output directing students to the HTML results
        file_url = f'file://{quote(html_result_path)}'
        # OSC 8 terminal hyperlink with bold and underline: ESC]8;;URL ESC\TEXT ESC]8;; ESC\
        esc = '\x1b'
        bold = f'{esc}[1m'
        underline = f'{esc}[4m'
        reset = f'{esc}[0m'
        link_text = f'{bold}{underline}{file_url}{reset}'
        hyperlink = f'{esc}]8;;{file_url}{esc}\\{link_text}{esc}]8;;{esc}\\'
        terminalreporter.write_sep('=', f'HTML Test Results View', bold=True, blue=True)
        terminalreporter.write_line(f'Open: {hyperlink} to view an HTML report of your test results.')
        modifier = 'Cmd' if sys.platform == 'darwin' else 'Ctrl'
        terminalreporter.write_line(
            f'Try [{modifier}]+[click] on the link above to open the HTML results in your browser.'
        )
