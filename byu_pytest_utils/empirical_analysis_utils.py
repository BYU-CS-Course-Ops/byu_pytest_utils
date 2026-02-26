import os
import json

from concurrent.futures import ProcessPoolExecutor
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
    error_message: str = "",
    preprocessing: Callable = lambda *x: x,
    postprocessing: Callable = lambda *x: x,
    output_group: list[int] = None,
):
    """
    Measure runtime of a process given inputs and write to a JSON file

    :param run: The process to run
    :param inputs: A list of tuples containing all input variations for `run`
    :param error_message: A message to output should the process fail
    :param preprocessing: A function that takes the current input and returns what will be passed to `run`
    :param postprocessing: A function that takes the return value of `run`
    :param output group: An ordered list of index numbers that determines what information from an input will be output to the JSON file

    """

    runtimes = []
    if output_group == None:
        output_group = list(range(len(inputs[0])))
    try:
        for input in inputs:
            print("Running with input", *input)
            passed_input = preprocessing(*input)

            if not isinstance(passed_input, (list, tuple)):
                passed_input = [passed_input]

            with ProcessPoolExecutor(max_workers=1) as executor:

                start = time()
                future = executor.submit(run, *passed_input)
                result = future.result()
                runtime = time() - start

                if not isinstance(result, (list, tuple)):
                    result = [result]

                postprocessing(*result)

                output = tuple(input[index] for index in output_group)
                runtimes.append((output, runtime))

    except KeyboardInterrupt:
        print("Cancelling...")
        executor.shutdown(wait=False, cancel_futures=True)
        print("Cancel complete")

    except RuntimeError as e:
        print(f"Process exited with error << {e} >>")
        print(error_message)

    # Print runtimes to a file

    output_folder = Path.cwd()
    filename = run.__name__ + "_runtimes.json"
    runtimes_file = os.path.join(output_folder, filename)
    with open(runtimes_file, "w") as file:
        json.dump(runtimes, file, indent=4)

    print()
    print(runtimes_file, "written")
