import argparse
import asyncio
import re
import runpy
import subprocess as sp
import sys
import traceback
import warnings
from collections import defaultdict
from functools import wraps
from pathlib import Path, PosixPath
from typing import Union

from byu_pytest_utils.edit_dist import edit_dist

DEFAULT_GROUP = '.'
DEFAULT_GROUP_NAME = 'everything-else'
MAX_PARTIAL_CREDIT = 1
GAP = '~'

PS = Union[Path, str]

TEST_RESULTS = defaultdict(list)

def _make_group_stats_decorator(group_stats):
    def decorator(func):
        # func should have empty (pass) body and no arguments
        def new_func(group_name):
            group_stat = group_stats[group_name]
            if not group_stat['passed']:
                assert group_stat['observed'] == group_stat['expected']
        new_func._group_stats = group_stats
        new_func.__name__ = func.__name__
        new_func.__module__ = func.__module__
        return new_func

    return decorator


def _ensure_absent(output_file):
    if output_file is not None:
        if isinstance(output_file, str):
            output_file = Path(output_file)
        output_file.unlink(missing_ok=True)


def _extract_input(dialog_contents: str):
    # Find all tokens delimited by << and >> and return them
    # as a list along with the original contents with the << and >> removed
    inputs = re.findall(r'<<(.*?)>>', dialog_contents, re.DOTALL)
    dialog_contents = re.sub(
        r'<<(.*?)>>', r'\1', dialog_contents, flags=re.DOTALL)
    return inputs, dialog_contents


def _extract_groups(dialog_contents: str):
    # blah blah [[foo;name;10]] blah blah

    group_weights = {DEFAULT_GROUP: 0}
    group_names = {
        DEFAULT_GROUP: DEFAULT_GROUP_NAME
    }

    group_sequence = ''

    # Iterate through the dialog contents
    # Characters not in a group are assigned to weight group 'a'
    # Each weight group is assigned the next letter of the alphabet
    # A group starts with [[ and ends with ]]
    # The semicolon separates the group text from the weight
    # All text in a group is assigned to the same weight group
    # e.g.
    # quux [[foo;test-foo;30]] bar [[baz;test-baz;20]] quux
    # produces groups: aaaaabbbaaaacccaaaa
    # and group_weights: {'-': 40, 'b': 30, 'c': 20}

    i = 0
    while i < len(dialog_contents):
        if dialog_contents[i:i + 2] == '``':
            # Start of a group
            group_symbol = chr(ord('a') - 1 + len(group_weights))
            group_match = re.search(
                r'``(.*?);(.+?);(\d+?)``', dialog_contents[i:], flags=re.DOTALL)
            group_text = group_match.group(1)
            group_name = group_match.group(2)
            group_names[group_symbol] = group_name
            group_weights[group_symbol] = int(group_match.group(3))
            group_sequence += group_symbol * len(group_text)
            i += group_match.end()
        else:
            # Not in a group
            group_sequence += DEFAULT_GROUP
            i += 1
    total = sum(group_weights.values())
    if total > 100:
        raise Exception('Group weights must add up to 100 or less')
    group_weights[DEFAULT_GROUP] = 100 - total

    # Then remove the groups from the dialog contents
    dialog_contents = re.sub(
        r'``(.*?);(.+?);(\d+?)``', r'\1', dialog_contents, flags=re.DOTALL)

    return group_weights, group_names, group_sequence, dialog_contents


def _score_observed_output(expected_output, observed_output):
    group_weights, group_names, group_sequence, dialog_contents = _extract_groups(expected_output)

    _, obs, exp = edit_dist(
        observed_output,
        dialog_contents,
        GAP=GAP
    )

    # insert gaps (i.e. DEFAULT_GROUP) into self.groups to match exp
    # then iterate over obs, exp, and groups
    # to compute rate of matches per group
    # (a gap in obs counts should use the prior group)
    # and return the score for each group
    # e.g. if groups is '---bbbcccc'
    # and group_weights is {'-': 50, 'b': 20, 'c': 30}
    # and exp is 'foobar~bazz'
    # and obs is 'boobarflaz~'
    # then groups should become '---bbbbcccc'

    if len(exp) - exp.count(GAP) != len(group_sequence):
        raise Exception('Too many gaps in expected output')

    group_ids = ''
    i = 0
    g = 0
    while i < len(exp):
        if exp[i] == GAP:
            group_ids += group_ids[-1] if group_ids else DEFAULT_GROUP
            i += 1
        else:
            group_ids += group_sequence[g]
            g += 1
            i += 1
    assert len(group_ids) == len(exp)

    # Compute group scores
    group_counts = {}
    group_matches = {}
    group_obs = {}
    group_exp = {}
    for obs_c, exp_c, group_id in zip(obs, exp, group_ids):
        if obs_c == exp_c:
            group_matches[group_id] = group_matches.get(group_id, 0) + 1
        group_counts[group_id] = group_counts.get(group_id, 0) + 1
        group_obs[group_id] = group_obs.get(group_id, '') + obs_c
        group_exp[group_id] = group_exp.get(group_id, '') + exp_c

    # Fix default group obs/exp
    # Use the full output, and pad with spaces to 80 chars
    def pad(text):
        return text + ' ' * (80 - len(text))

    group_obs[DEFAULT_GROUP] = pad(
        obs)
    group_exp[DEFAULT_GROUP] = pad(
        exp)

    group_stats = {}
    for group_id, group_name in group_names.items():
        if group_id not in group_counts:
            # For example, the DEFAULT_GROUP sometimes has no hits
            continue
        group_max = group_weights[group_id] / 100
        group_stats[group_name] = {
            'group_name': group_name,
            'expected': group_exp[group_id],
            'observed': group_obs[group_id],
            'score': group_matches.get(group_id, 0) / group_counts[group_id] * group_max,
            'max_score': group_max,
            'passed': group_max == 0 or group_matches.get(group_id, -1) == group_counts[group_id],
        }

    return group_stats


def _consolidate_stats(name, stats):
    return {
        'name': name,
        'expected': stats['everything-else']['expected'],
        'observed': stats['everything-else']['observed'],
        'score': round(sum(group['score'] for group in stats.values()), 3),
        'max_score': round(sum(group['max_score'] for group in stats.values()), 3),
        'passed': all(group['passed'] for group in stats.values()),
    }


def _score_output(
        expected_io: str, observed_io: str,
        expected_files: list[tuple[Path, Path]]
):
    # ORIGINAL - per-group test results
    # group_stats = { }
    # group_stats.update({'stdout-' + k: v for k, v in _score_observed_output(expected_io, observed_io).items()})
    # for exp_file, obs_file in expected_files:
    #     if not obs_file.exists():
    #         obs_content = f'File not found: {obs_file}. Did you write it?'
    #     else:
    #         obs_content = obs_file.read_text()
    #     group_stats.update(
    #         {exp_file.name + '-' + k: v for k, v in _score_observed_output(exp_file.read_text(), obs_content).items()})
    #
    # return group_stats

    group_stats = {}
    if expected_io is not None:
        stats = _score_observed_output(expected_io, observed_io)
        group_stats['stdout'] = _consolidate_stats('stdout', stats)

    for exp_file, obs_file in expected_files:
        if not obs_file.exists():
            obs_content = f'File not found: {obs_file}. Did you write it?\n' + observed_io
        else:
            obs_content = obs_file.read_text()
        stats = _score_observed_output(exp_file.read_text(), obs_content)
        group_stats[exp_file.name] = _consolidate_stats(exp_file.name, stats)


    return group_stats


async def _read_stream(stream: asyncio.StreamReader, timeout: float, output_limit: int):
    """
    Reads the stream until the end of the current content
    Stops waiting for content after `timeout` seconds
    Returns decoded content (i.e. str not bytes)
    """
    buffer = []

    while True:
        try:
            token = await asyncio.wait_for(stream.read(1), timeout)
            if not token:
                # stream.read() returns an empty byte when EOF is reached
                break
            token = token.decode()
            buffer.append(token)
            if len(buffer) > output_limit:
                break

        except asyncio.TimeoutError:
            # No bytes have been written for at least `timeout` seconds
            break

    return ''.join(buffer)


async def _run_with_timeout(waitable, timeout):
    fut = asyncio.Future()

    t1 = asyncio.create_task(waitable)
    t2 = asyncio.create_task(asyncio.sleep(timeout))

    def _timeout(t):
        fut.set_exception(TimeoutError)

    t2.add_done_callback(_timeout)
    t1.add_done_callback(lambda t: t2.remove_done_callback(_timeout) and fut.set_result(t.result))

    return await fut


async def _run_exec_with_io(
        exec: list[str],
        inputs: list[str],
        read_timeout: float,
        finish_timeout: float,
        max_output_size: int = 10000
) -> tuple[str, str]:
    """
    Run an executable. Provided content via STDIN. Capture STDOUT.
    :param exec: executable and arguments
    :param inputs: list of inputs to executable
                   assumes newlines have been added if they are necessary
    :param read_timeout: how long to wait after a byte is written to STDOUT before returning
    :return: Nothing. But output and error will be populated when finished.
    """
    output_size = 0
    output = []
    error = []

    print(' '.join(exec))
    PIPE = asyncio.subprocess.PIPE
    proc = await asyncio.create_subprocess_exec(
        *exec, stdin=PIPE, stdout=PIPE, stderr=asyncio.subprocess.STDOUT)

    timeout_task = asyncio.create_task(asyncio.sleep(finish_timeout))

    def kill(t):
        error.append('The program failed to finish in the expected amount of time; do you have an infinite loop?')
        proc.kill()

    timeout_task.add_done_callback(kill)

    output.append(await _read_stream(proc.stdout, read_timeout, max_output_size - output_size))
    output_size += len(output[-1])
    print(output[-1], end='')
    if output_size > max_output_size:
        error.append(f'Program output exceeded limit of {max_output_size} characters')
        proc.kill()
        inputs = []  # i.e. skip the input loop and cut to the finish

    for i in range(len(inputs)):
        content = inputs[i]
        if proc.returncode is not None:
            # Process has completed
            error.append('The program exited before all inputs were provided')
            break

        output.append(content)
        output_size += len(output[-1])
        print(output[-1], end='')

        proc.stdin.write(content.encode())
        await proc.stdin.drain()

        if i == len(inputs) - 1:
            # close stdin
            proc.stdin.close()

        response = await _read_stream(proc.stdout, read_timeout, max_output_size - output_size)

        output.append(response)
        output_size += len(output[-1])
        print(output[-1], end='')
        if output_size > max_output_size:
            error.append(f'Program output exceeded limit of {max_output_size} characters')
            proc.kill()
            break

    proc.stdin.close()
    code = await proc.wait()

    timeout_task.remove_done_callback(kill)
    timeout_task.cancel()

    if code != 0:
        error.append(f'The program returned a non-zero exit code: {code}')

    return ''.join(output), '\n'.join(error)


def _run_exec(executable, *args, inputs=None, read_timeout=1, run_timeout=60):
    args = [executable, *(str(a) for a in args)]

    output, error = asyncio.run(_run_exec_with_io(
        args, [c + '\n' for c in (inputs or [])],
        read_timeout=read_timeout, finish_timeout=run_timeout
    ))

    if error:
        output += '\nError: ' + error

    return output


def _run_script(
        script_name, *args,
        inputs: list[str] = None,
        module='__main__',
        echo_output=True
):
    if inputs is None:
        inputs = []

    # Intercept input, print, and sys.argv
    sys.argv = [script_name, *(str(a) for a in args)]

    output_tokens = []

    @wraps(input)
    def _py_input(prompt=''):
        output_tokens.append(prompt)
        if not inputs:
            raise Exception("input() called more times than expected")
        input_text = inputs.pop(0)
        output_tokens.append(input_text + '\n')
        if echo_output:
            print(input_text)
        return input_text

    @wraps(print)
    def _py_print(*values, **kwargs):
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        res = sep.join(str(t) for t in values) + end
        output_tokens.append(res)

    _globals = {
        'input': _py_input,
        'print': _py_print,
        'sys': sys
    }

    # Run script as __main__
    try:
        runpy.run_path(script_name, _globals, module)

    except Exception as ex:
        if isinstance(script_name, Path):
            script_name = script_name.name

        # get stack trace as string
        stack_trace = traceback.format_exc().split('\n')
        # Find index of first line that contains the script name
        index = 0
        for i, line in enumerate(stack_trace):
            if script_name in line:
                index = i
                break
        stack_trace = "\n".join(stack_trace[index:])
        output_tokens.append(f"\nException: {ex}\n{stack_trace}")
        
    return ''.join(output_tokens)


def _run_dialog(runner,
                executable, *args,
                expected_stdio: PS = None,
                expected_files: list[tuple[PS, PS]] = None,
                **kwargs) -> dict:
    if expected_stdio is not None and not isinstance(expected_stdio, Path):
        expected_stdio = Path(expected_stdio)

    to_path = lambda f: Path(f) if not isinstance(f, Path) else f
    expected_files = [
        (to_path(ex), to_path(ob)) for ex, ob in (expected_files or [])
    ]

    try:
        # Ensure the output files aren't leftover from a previous run
        for _, obs_file in expected_files:
            _ensure_absent(obs_file)

        if callable(executable):
            executable = executable()

        args = [arg() if callable(arg) else arg for arg in args]

        # Run the script
        if expected_stdio is not None:
            inputs, expected_io = _extract_input(expected_stdio.read_text())
        else:
            inputs = []
            expected_io = None

        output = runner(
            executable, *args,
            inputs=inputs, **kwargs
        )

        # Score results
        group_stats = _score_output(
            expected_io, output, expected_files
        )

    except Exception as ex:
        group_stats = {
            'load-tests': {
                'group_name': 'load-tests',
                'expected': '',
                'observed': traceback.format_exc(),
                'score': 0,
                'max_score': 1,
                'passed': False,
            }
        }

    return group_stats


def run_exec(executable, *args,
             expected_stdio: PS = None,
             expected_files: list[tuple[PS, PS]] = None,
             read_timeout=1) -> dict:
    return _run_dialog(
        _run_exec, executable, *args,
        expected_stdio=expected_stdio,
        expected_files=expected_files,
        read_timeout=read_timeout)


def run_script(script_name, *args,
               expected_stdio: Path = None,
               expected_files: list[tuple[Path, Path]] = None,
               module='__main__',
               echo_output=True
               ) -> dict:
    return _run_dialog(
        _run_script, script_name, *args,
        expected_stdio=expected_stdio,
        expected_files=expected_files,
        module=module, echo_output=echo_output)


#
# Deprecated
#

def dialog_exec(dialog_file, executable, *args, output_file=None,
                read_timeout=1, **deprecated):
    if deprecated:
        for argument in deprecated:
            warnings.warn(f'Argument {argument} is no longer supported')

    if output_file is not None:
        group_stats = run_exec(executable, *args,
                               expected_files=[(dialog_file, output_file)],
                               read_timeout=read_timeout)
    else:
        group_stats = run_exec(executable, *args,
                               expected_stdio=dialog_file,
                               read_timeout=read_timeout)

    return _make_group_stats_decorator(group_stats)

def dialog(dialog_file, script, *script_args, output_file=None):
    from . import _get_caller_folder

    script = (_get_caller_folder() / script).resolve()

    if output_file is not None:
        group_stats = run_script(script, *script_args,
                                 expected_files=[(dialog_file, output_file)])
    else:
        group_stats = run_script(script, *script_args, expected_stdio=dialog_file)

    return _make_group_stats_decorator(group_stats)


def record_script(dialog_file, script_name, *script_args):
    # Intercept input, print, and sys.argv
    sys.argv = [script_name, *(str(a) for a in script_args)]
    with open(dialog_file, 'w') as file:
        def _input(prompt):
            file.write(prompt)
            response = input(prompt)
            file.write(f'<<{response}>>\n')
            return response

        def _print(*args, **kwargs):
            print(*args, **kwargs)
            print(*args, **kwargs, file=file)

        _globals = {
            'input': _input,
            'print': _print,
            'sys': sys
        }

        # Run script as __main__
        result = runpy.run_path(script_name, _globals, '__main__')

    return result


def record_exec(dialog_file, executable, *args):
    raise NotImplemented()

    args = [executable, *(str(a) for a in args)]
    with open(dialog_file, 'w') as file:
        process = sp.Popen(args, stdin=sp.PIPE,
                           stdout=sp.PIPE, stderr=sp.STDOUT)
        for line in _exec_read_stdout_with_timeout(process):
            if line is None:
                input_to_give = input()
                process.stdin.write((input_to_give + '\n').encode())
                process.stdin.flush()
                file.write(f'<<{input_to_give}>>\n')
                continue
            print(line, end='')
            file.write(line)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('dialog_file', help='Dialog file to write')
    parser.add_argument('to_run', help='Python script or executable to run')
    parser.add_argument('args', nargs='*',
                        help='Arguments (if any) to the Python script or executable')
    parser.add_argument('-e', '--exec', action='store_true',
                        help='Interpret `to_run` as an executable instead of a Python script')
    args = parser.parse_args()

    if args.exec:
        record_exec(args.dialog_file, args.to_run, *args.args)
    else:
        record_script(args.dialog_file, args.to_run, *args.args)
