import json
import matplotlib.pyplot as plt
import sys
import os

from pathlib import Path
from time import time
from typing import Callable


def compute_average_runtimes(runtimes):
    """Compute average runtimes of `measure_runtime` JSON file output"""

    groups = {}
    for size, runtime in runtimes:
        key = tuple(size)
        if key not in groups:
            groups[key] = []
        groups[key].append(runtime)

    return [
        (
            *size,
            round(sum(stats) / len(stats), 3),
        )
        for size, stats in groups.items()
    ]


def print_markdown_table(
    ave_runtimes: list[tuple], headers: list[str] = ["Size", "Time (sec)"]
):
    """Print the result of `compute_average_runtimes` in markdown table format."""

    header_widths = [len(header) for header in headers]

    rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("-" * len(header) for header in headers) + " |",
    ]

    rows += (
        "| "
        + " | ".join(f"{field:<{width}}" for field, width in zip(row, header_widths))
        + " |"
        for row in ave_runtimes
    )

    print()
    print("Copy this markdown table into your report:")
    print()
    print("\n".join(rows))
    print()


def measure_runtime(
    run: Callable,
    inputs: list[tuple],
    runtime_scalar: int = 1,
    preprocessing: Callable = lambda *x: x,
    postprocessing: Callable = lambda *x: x,
    output_group: list[int] = None,
    recursion_limit: int = None,
):
    """
    Measure runtime of a process given inputs and write to a JSON file

    :param run: The process to run
    :param inputs: A list of tuples containing all input variations for `run`
    :param runtime_scalar: An integer to multiply your runtime by. Default is 1 (seconds)
    :param preprocessing: A function that takes the current input and returns what will be passed to `run`
    :param postprocessing: A function that takes the return value of `run`
    :param output_group: An ordered list of index numbers that determines what information from an input will be output to the JSON file
    :param recursion_limit: Allows you to raise Python recursion limit if running as a child process
    """

    output_folder = Path.cwd()
    filename = run.__name__ + "_runtimes.json"
    runtimes_file = os.path.join(output_folder, filename)

    with open(runtimes_file, "w") as f:
        json.dump("", f, indent=4)

    if output_group == None:
        output_group = list(range(len(inputs[0])))

    if recursion_limit:
        sys.setrecursionlimit(recursion_limit)

    for input in inputs:
        print("Running with input", *input)
        passed_input = preprocessing(*input)

        if not isinstance(passed_input, (list, tuple)):
            passed_input = [passed_input]

        start = time()
        result = run(*passed_input)
        runtime = (time() - start) * runtime_scalar

        if not isinstance(result, (list, tuple)):
            result = [result]

        postprocessing(*result)

        output = tuple(input[index] for index in output_group)

        with open(runtimes_file, "r") as f:
            runtimes = list(json.load(f))

        runtimes.append((output, runtime))

        with open(runtimes_file, "w") as file:
            json.dump(runtimes, file, indent=4)

    print()
    print("Runtimes complete")


def _compute_coefficients(observed_performance, theoretical_order):
    return [time / theoretical_order(*n) for n, time in observed_performance]


def compute_coefficient(filename, big_o, start, end):

    with open(filename, "r") as f:
        runtimes = json.load(f)

    coeffs = _compute_coefficients(runtimes, big_o)

    used_coeffs = coeffs[start:end]

    coeff = sum(used_coeffs) / len(used_coeffs)
    print(coeff)

    plt.bar(range(len(coeffs)), coeffs)
    xlim = plt.xlim()
    plt.plot(xlim, [coeff, coeff], ls=":", c="k")
    plt.xlim(xlim)
    plt.title(f"coeff={coeff}")
    plt.show()
