import importlib
import re
import json
import os.path
import runpy
from functools import wraps
from pathlib import Path
import inspect
from typing import Union
from dataclasses import dataclass

from byu_pytest_utils.html.html_renderer import TestResults, get_test_order

import pytest
import sys


@dataclass
class TestInfo:
    name: str
    points: float
    result: dict


def run_python_script(script, *args, module='__main__'):
    """
    Run the python script with arguments

    If the script expects STDIN, use the dialog framework instead

    :param script: Python script to run
    :param args: Arguments to the python script
    :param module: Defaults to '__main__'
    :return: Namespace as a result of running the script
    """
    if not os.path.exists(script):
        pytest.fail(f'The file {script} does not exist. Did you submit it?')

    def _input(*args):
        raise Exception("input function not supported for this test")

    sys.argv = [script, *(str(a) for a in args)]
    _globals = {
        'sys': sys,
        'input': _input
    }
    return runpy.run_path(script, _globals, module)


def parse_test_tier(test_tier: str, test_results: list[TestResults]) -> json:
    """
    Create a single json object for a test set from the test results and tally the scores for each test in the test set

    :param test_tier: Name of the test tier
    :param test_results: List of test results
    :return: JSON object with test set information
    """
    test_set_results = {
        'name': test_tier,
        'output': '',
        'output_format': 'html',
        'max_score': 0,
        'score': 0,
        'visibility': 'visible'
    }

    status = 'passed'
    for test_result in test_results:
        if test_result.test_tier == test_tier:
            test_set_results['max_score'] += test_result.max_score
            if test_result.passed:
                test_set_results['score'] += test_result.score
            if not test_result.passed:
                status = 'failed'

    return test_set_results, status


def get_gradescope_results(test_results:list[TestResults], html_results):
    """
    Get the gradescope results from the test_info and html_results

    :param test_results: Dictionary of test information
    :param html_results: HTML-rendered output from comparison
    :return: Dictionary in Gradescope-compatible format
    """
    test_order = get_test_order(test_results)

    if test_results[0].__dict__.get('test_tier'):
        gradescope_results = {
            'tests': []
        }

        prior_failed = False

        for test_set in test_order:
            test_set_results, status = parse_test_tier(test_set, test_results)

            test_set_results['output'] = html_results.pop(0)
            test_set_results['status'] = status
            if prior_failed:
                test_set_results['score'] = 0
                test_set_results['status'] = 'failed'
            elif status == 'failed':
                prior_failed = True

            gradescope_results['tests'].append(test_set_results)

        return gradescope_results

    else:
        return {
            'tests': [
                {
                    'name': test_result.test_name,
                    'output': report,
                    'output_format': 'html',
                    'score': round(test_result.score, 3),
                    'max_score': round(test_result.max_score, 3),
                    'visibility': 'visible',
                    'status': 'passed' if test_result.passed else 'failed'
                }
                for test_result, report in zip(test_results, html_results)
            ]
        }


def bake_css(css: str, results: dict) -> dict:
    """Simple CSS inlining - extracts styles and applies to matching elements."""

    if not css.strip():
        return results

    # Extract CSS rules using simple regex
    css_rules = {}

    # Find all CSS rules: selector { declarations }
    for match in re.finditer(r'([.#]?[\w-]+)\s*\{\s*([^}]+)\s*\}', css):
        selector = match.group(1).strip()
        declarations = match.group(2).strip()
        css_rules[selector] = declarations

    # Apply to each test result
    for result in results.get('tests', []):
        if 'output' in result and result['output']:
            html = result['output']

            # Apply class styles (.classname)
            for selector, style in css_rules.items():
                if selector.startswith('.'):
                    class_name = selector[1:]
                    # Find elements with this class and add inline style
                    pattern = f'(<[^>]*class=["\'][^"\']*{re.escape(class_name)}[^"\']*["\'][^>]*?)>'
                    replacement = f'\\1 style="{style}">'
                    html = re.sub(pattern, replacement, html)

                elif selector.startswith('#'):
                    # ID selector (#idname)
                    id_name = selector[1:]
                    pattern = f'(<[^>]*id=["\']?{re.escape(id_name)}["\']?[^>]*?)>'
                    replacement = f'\\1 style="{style}">'
                    html = re.sub(pattern, replacement, html)

            result['output'] = html

    return results


def quote(url: str) -> str:
    """Escape characters in file path for browser compatibility."""
    return url.replace(' ', '%20').replace('\\', '/')


def ensure_missing(file: Union[Path, str]):
    """
    Use the decorator to ensure the provided file is always missing
    when the test starts
    """
    if isinstance(file, str):
        file = Path(file)
    def decorator(func):
        @wraps(func)
        def new_func(*args, **kwargs):
            file.unlink(missing_ok=True)
            return func(*args, **kwargs)

        return new_func

    return decorator


def with_import(module_name=None, function_name=None):
    # Create a decorator
    def decorator(test_function):
        # Import function_name from module_name, then run function
        # with function_name passed in as first arg
        nonlocal function_name
        nonlocal module_name
        params = inspect.signature(test_function).parameters
        first_param = next((pname for pname, _ in params.items()))
        function_name = function_name or first_param
        module_name = module_name or function_name

        @wraps(test_function)
        def new_test_function(*args, **kwargs):
            try:
                module = importlib.import_module(module_name)
                func = getattr(module, function_name)
                return test_function(func, *args, **kwargs)

            except ModuleNotFoundError as err:
                pytest.fail(
                    f'{type(err).__name__}: {err}\n'
                    f'Unable to load {module_name}.py. '
                    f'Was {module_name}.py submitted?'
                )
            except ImportError as err:
                pytest.fail(
                    f'{type(err).__name__}: {err}\n'
                    f'Unable to load {module_name}.py. '
                    f'Are there errors in the file?'
                )
            except KeyError as err:
                pytest.fail(
                    f'{type(err).__name__}: {err}\n'
                    f'Unable to load {function_name} from {module_name}.py. '
                    f'Is {function_name} defined?'
                )

        # Modify signature to look like test_function but without
        # anything filled by with_import
        sig = inspect.signature(test_function)
        sig._parameters = dict(sig.parameters)
        del sig._parameters[first_param]
        new_test_function.__signature__ = sig

        return new_test_function

    if callable(module_name):
        # The decorator was used without arguments,
        # so this call is the decorator
        func = module_name
        module_name = None
        return decorator(func)
    else:
        return decorator
