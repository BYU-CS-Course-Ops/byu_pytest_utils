import json
import sys
import os
import math
import multiprocessing as mp

from queue import Empty
from pathlib import Path
from time import time
from typing import Callable, TypeVar, Protocol, Any, TextIO
from collections.abc import Iterable

# ------------------------------------------------------------------------------
# ----- Types & misc utilities -------------------------------------------------
# ------------------------------------------------------------------------------


_T_In = TypeVar("_T_In")
_T_Out = TypeVar("_T_Out")
_T_Trial = TypeVar("_T_Trial")

ReportFn = Callable[[float], None]
SubjectFn = Callable[[_T_In], _T_Out]

def noop(*args, **kwargs) -> None:
    """
    Does nothing.
    :return: Nothing.
    """
    pass


# ------------------------------------------------------------------------------
# ----- Instruments ------------------------------------------------------------
# ------------------------------------------------------------------------------

class Instrument[_T_In, _T_Out](Protocol):
    def __call__(self, f: SubjectFn, report: ReportFn) -> SubjectFn:
        ...

class InstrumentRuntime[_T_In, _T_Out](Instrument[_T_In, _T_Out]):
    def __init__(self, runtime_scalar: float = 1):
        """
        An instrument that measures the running time of the subject function. 

        :param runtime_scalar: How much to scale runtime by.
        `1` for seconds, `1000` for milliseconds, etc.
        """
        self.runtime_scalar = runtime_scalar
    
    def __call__(self, f: SubjectFn, report: ReportFn) -> SubjectFn:
        def f2(x: _T_In) -> _T_Out:
            start = time()
            result = f(x)
            runtime = (time() - start) * self.runtime_scalar
            report(runtime)
            return result
        return f2

class InstrumentPostprocess[_T_In, _T_Out](Instrument[_T_In, _T_Out]):
    def __init__(self, postprocess: Callable[[_T_In, _T_Out], _T_Out]):
        """
        An instrument that applies a post-processing function
        to each trial, possibly replacing or otherwise altering the output for later stages.

        :param postprocess: The function to apply; the return value replaces the old output value.
        See type signature for more info.
        """
        self._postprocess = postprocess
    
    def __call__(self, f: SubjectFn, report: ReportFn) -> SubjectFn:
        return lambda x: self._postprocess(x, f(x))


def instrument_numeric_inputs(f: Callable[[Iterable[Any]], _T_Out], report: ReportFn) -> Callable[[Iterable[Any]], _T_Out]:
    def f2(inputs: Iterable[Any]) -> _T_Out:
        for x in inputs:
            y: float
            try:
                y = float(x)
            except ValueError:
                y = math.nan
            report(y)
        return f(inputs)
    return f2        


# ------------------------------------------------------------------------------
# ----- Results ----------------------------------------------------------------
# ------------------------------------------------------------------------------

def mean_aggregator(rows: list[list[float]]) -> list[float]:
    result = [0.0] * len(rows[0])
    for row in rows:
        for i, x in enumerate(row):
            result[i] += x
    for i in range(len(result)):
        result[i] /= len(rows)
    return result

class ExperimentResults:
    def __init__(self, rows: list[list[float]]):
        self.width = -1
        if not isinstance(rows, list):
            raise TypeError("Experiment results: not a list")
        for row in rows:
            if not isinstance(row, list):
                raise TypeError("Experiment results: row is not a list")

            if self.width == -1:
                self.width = len(row)
            elif len(row) != self.width:
                raise ValueError("Experiment results: rows differ in length")

            for i in range(self.width):
                try:
                    row[i] = float(row[i])
                except Exception:
                    raise TypeError(f"Experiment results: entry {row[i]} is non-numeric")
        self.rows = rows

    @staticmethod
    def legacy_load(filename: str) -> "ExperimentResults":
        """
        This is deprecated; use `load` instead!
        Load experiment results from a file using the legacy format.
        """
        rows: Any
        with open(filename, "r") as f:
            rows = json.load(f)

        return ExperimentResults([x[0] + [x[1]] for x in rows])


    @staticmethod
    def load(filename: str) -> "ExperimentResults":
        """
        Load experiment results from a file using an unspecified format.
        """
        rows: Any
        with open(filename, "r") as f:
            rows = json.load(f)

        return ExperimentResults(rows)

    def legacy_dump(self, filename: str):
        """
        This is deprecated; use `dump` instead!
        Dump experiment results to a file using the legacy format.
        """
        transformed_rows = [(row[:-1], row[-1]) for row in self.rows]
        with open(filename, "w+") as f:
            json.dump(transformed_rows, f)

    def dump(self, filename: str, overwrite: bool = True):
        """
        Dump experiment results to a file using an unspecified format.
        """
        flags = "w+" if overwrite else "x"
        with open(filename, flags) as f:
            json.dump(self.rows, f)

    def aggregate(self, key_columns: list[int], aggregator: Callable[[list[list[float]]], list[float]] = mean_aggregator) -> "ExperimentResults":
        """
        Creates a new `ExperimentResults` by selecting certain rows to be keys,
        and aggregating rows together that share the same key.

        By default, aggregation just takes the mean.

        :param key_columns: The indeces of the columns containing the keys
        to be projected onto.
        :param aggregator: A function which aggregates a list of rows
        with the same key into a single row. The aggregator should not modify any of
        the rows it is given.
        """
        lookup: dict[tuple, list[list[float]]] = {}
        for row in self.rows:
            key = tuple([row[i] for i in key_columns])
            if key not in lookup:
                lookup[key] = []
            lookup[key].append(row)
        new_rows = [aggregator(v) for v in lookup.values()]
        return ExperimentResults(new_rows)

    def constants_of_proportionality(self, model: Callable, independents: list[int], dependents: list[int]) -> tuple[list[float], list[list[float]]]:
        """
        Computes the constant of proportionality for each dependent variable
        against the predictions of a model function.

        :returns: The constant of proportionality for each dependent variable,
        together with the ratios involved (grouped by column).
        """
        ratios: list[list[float]] = [[] for _ in dependents]
        for row in self.rows:
            expected = model(*[row[indep_col] for indep_col in independents])
            if not isinstance(expected, list | tuple):
                expected = (expected,)
            for i, dep_col in enumerate(dependents):
                ratios[i].append(row[dep_col] / expected[i])
        return [sum(col) / len(col) for col in ratios], ratios

    
    def write_markdown_table(self, columns: list[tuple[int, str, int, int]], stream: TextIO = sys.stdout):
        """
        Print the experiment results in markdown table format.

        Each column to be displayed is represented by a 4-tuple `(column index, column heading, width, precision)`.
        """
        cells = [
            [col[1] for col in columns]
        ]
        widths = [len(col[1]) for col in columns]
        for row in self.rows:
            s_row = []
            for table_idx, (col_idx, heading, width, prec) in enumerate(columns):
                x = row[col_idx]
                s = f"{x: {width}.{prec}f}"
                # We could infer the widths using the formatting
                # strategy, but it doesn't hurt to be a bit defensive.
                if len(s) > widths[table_idx]:
                    widths[table_idx] = len(s)
                s_row.append(s)
            cells.append(s_row)

        def write_row(row):
            nonlocal widths
            stream.write("| ")
            for i, (cell, width) in enumerate(zip(row, widths)):
                stream.write(cell)
                gap = widths[0] - len(cell)
                stream.write(" " * gap)
                if i + 1 == len(row):
                    stream.write(" |\n")
                else:
                    stream.write(" | ")

        write_row(cells[0])
        write_row(["-" * w for w in widths])
        for i in range(1, len(cells)):
            write_row(cells[i])

    def display_constant_of_proportionality_report(self, model: Callable, independents: list[int], dependents: list[int], dependent_names: list[str]):
        import matplotlib.pyplot as plt
    
        means, ratio_table = self.constants_of_proportionality(model, independents, dependents)
        for dep_name, mean, ratios in zip(dependent_names, means, ratio_table):
            print(f"Constant of proportionality for {dep_name}:")
            print(f"  {mean}")
            plt.bar(range(len(ratios)), ratios)
            xlim = plt.xlim()
            plt.plot(xlim, [mean, mean], ls=":", c="k")
            plt.title(f"Actual/predicted ratios for {dep_name}")
            plt.show()
            input("Enter to continue...")
            plt.close()

    def print_markdown_and_prompt_copy(self, columns: list[tuple[int, str, int, int]]):
        print("\nCopy this markdown table into your report:\n")
        self.write_markdown_table(columns)
        print()


# ------------------------------------------------------------------------------
# ----- Listeners --------------------------------------------------------------
# ------------------------------------------------------------------------------

EXPERIMENT_EVENT_BEGIN_TRIAL = "begin_trial"
EXPERIMENT_EVENT_SUCCESS = "success"
EXPERIMENT_EVENT_TIMEOUT = "timeout"
EXPERIMENT_EVENT_PARENT_EXCEPTION = "parent_exception"
EXPERIMENT_EVENT_QUEUE_EXCEPTION = "queue_exception"
EXPERIMENT_EVENT_CHILD_EXCEPTION = "child_exception"
EXPERIMENT_EVENT_CANCEL_SIGNALED = "cancel_signalled"
EXPERIMENT_EVENT_CANCEL_COMPLETE = "cancel_complete"

def experiment_listener_stdout(event: str, arg: Any):
    """
    An experiment listener that prints experiment events to the console.  
    """
    if event == EXPERIMENT_EVENT_BEGIN_TRIAL:
        fmt: str
        if isinstance(arg, list | tuple):
            fmt = ", ".join(map(str, arg))
        else:
            fmt = str(arg)
        print(f"Running trial {fmt}")
    elif event == EXPERIMENT_EVENT_SUCCESS:
        print("\nExperiment complete!")
    elif event == EXPERIMENT_EVENT_TIMEOUT:
        print("\nTrial timed out!")
    elif event == EXPERIMENT_EVENT_PARENT_EXCEPTION:
        print(f"\nInternal parent process error << {arg} >>")
    elif event == EXPERIMENT_EVENT_QUEUE_EXCEPTION:
        print(f"\nQueue closed with error << {arg} >>")
    elif event == EXPERIMENT_EVENT_CHILD_EXCEPTION:
        print(f"\nChild process exited with error << {arg} >>")
    elif event == EXPERIMENT_EVENT_CANCEL_SIGNALED:
        print("\nCancelling...")
    elif event == EXPERIMENT_EVENT_CANCEL_COMPLETE:
        print("Cancel complete")

# ------------------------------------------------------------------------------
# ----- Experiment -------------------------------------------------------------
# ------------------------------------------------------------------------------

def experiment_preprocess_noop(x: _T_In) -> _T_In:
    return x

experiment_setup_default = noop
experiment_cleanup_default = noop

class Experiment[_T_Trial, _T_In, _T_Out]:
    def __init__(
        self,
        subject: SubjectFn,
        preprocess: Callable[[_T_Trial], _T_In],
        setup: Callable[[], None] = experiment_setup_default,
        cleanup: Callable[[], None] = experiment_cleanup_default,
    ):
        """
        Construct a new experiment.

        :param subject: The function being measured.
        :param preprocess: This is run to transform a trial input into the form
        that the subject function expects. Crucially, this stage is not measured,
        meaning expensive operations (graph generation, e.g.) can be performed here.
        :param setup: This is run in the experiment's process before any trials begin.
        :param cleanup: This is run in the experiment's process after all trials finish,
        so long as the process is not killed by the operating system or a keyboard interrupt.

        All function parameters should be pickleable, so no closures.
        """
        self._subject = subject
        self._preprocess = preprocess
        self._instruments: list[Instrument[_T_In, _T_Out]] = []
        self._setup = setup
        self._cleanup = cleanup
       
    def add_instrument(self, instrument: Instrument[_T_In, _T_Out]) -> int:
        """
        Adds a new instrument to this experiment.

        An instrument is a function that takes two arguments:
        a function to transform, and a `report` function
        used to report measurements relevant to the experiment.

        As an example, the following instrument records the
        floating-point return value of the subject function:
        
        ```
        def instrument_output(subject, report):
            def transformed_subject(x):
                result = subject(x)
                report(result)
                return result
            return transformed_subject
        ```

        Instruments should be able to be pickled,
        as they are transferred between processes.
        This means that instruments should **not** be
        closures; use a class with the `__call__`
        method instead.
        
        Instruments are applied in the order they are added;
        in practice, this means that instruments that measure
        runtime properties like time and space should come *first*,
        to avoid other instruments affecting measurements.

        :param instrument: The instrument to be added.
        :return: An ID that may be used to refer to this instrument later.
        """
        self._instruments.append(instrument)
        return len(self._instruments) - 1

    def run(self,
            trials: list[_T_Trial],
            output_selector: list[tuple[int, int]],
            timeout: float | None = None,
            listener: Callable[[str, Any], Any]= experiment_listener_stdout
        ) -> ExperimentResults:
        """
        Runs the experiment on a list of trial inputs.

        The experiment is run in a separate process to ensure that errors
        and resource exhaustion can be gracefully recovered from.

        :param trials: The trial inputs to run the experiment on.

        :param output_selector: A list of (instrument ID, result index)
        tuples specifying the raw instrument outputs that will be included
        in each row of the result. For instance, if we want each row to
        contain the first output of instrument 0 followed by the second output
        of instrument 3, we would use `output_selector = [(0, 0), (3, 1)]`.

        :param timeout: How long to wait for the child process to respond for each
        trial before giving up and killing it.
        
        :param listener: A function that handles various experiment events.
        Defaults to notifying `stdout`.
        
        :return: The results of the experiment, containing all rows that were
        successfully produced.
        """      
        data: list[list[float]] = []
        queue: mp.Queue[list[float] | str] = mp.Queue()
        process = mp.Process(target=_run_experiment, args=(queue, self, trials, output_selector))
        success = True
        try:
            process.start()
            for trial in trials:
                listener(EXPERIMENT_EVENT_BEGIN_TRIAL, trial)
                x: list[float] | str
                try:
                    x = queue.get(timeout=timeout)
                except Empty:
                    listener(EXPERIMENT_EVENT_TIMEOUT, None)
                    process.kill()
                    success = False
                    break
                except Exception as e:
                    listener(EXPERIMENT_EVENT_QUEUE_EXCEPTION, e)
                    process.kill()
                    success = False
                    break
                if isinstance(x, str):
                    listener(EXPERIMENT_EVENT_CHILD_EXCEPTION, x)
                    break
                data.append(x)
            process.join()
            if success:
                listener(EXPERIMENT_EVENT_SUCCESS, None)
        except KeyboardInterrupt:
            listener(EXPERIMENT_EVENT_CANCEL_SIGNALED, None)
            process.kill()
            process.join()
            listener(EXPERIMENT_EVENT_CANCEL_COMPLETE, None)
        except Exception as e:
            listener(EXPERIMENT_EVENT_PARENT_EXCEPTION, e)
            process.kill()
            process.join()
        finally:
            process.close()
            queue.close()
        return ExperimentResults(data)


def _run_experiment(
    queue: "mp.Queue[list[float] | str]",
    experiment: Experiment[_T_Trial, _T_In, _T_Out],
    trials: list[_T_Trial],
    output_selector: list[tuple[int, int]],
):
    experiment._setup()
    try:
        fn = experiment._subject
        results_by_instrument: list[list[float]] = []
        
        for instrument in experiment._instruments:
            instrument_results: list[float] = []
            results_by_instrument.append(instrument_results)
            fn = instrument(fn, instrument_results.append)

        for trial in trials:
            fn(experiment._preprocess(trial))
            row = [results_by_instrument[instrument_id][index] for (instrument_id, index) in output_selector]
            queue.put(row)
            for instrument_results in results_by_instrument:
                instrument_results.clear()
    except Exception as e:
        queue.put(str(e))
    finally:
        experiment._cleanup()
        

# ------------------------------------------------------------------------------
# ----- Backward compatibility -------------------------------------------------
# ------------------------------------------------------------------------------

def compute_average_runtimes(runtimes):
    """
    This is deprecated! See the aggregator API on `ExperimentResults`.

    Compute average runtimes of `measure_runtime` JSON file output
    """
    groups = {}
    for size, runtime in runtimes:
        key = (size,)
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
    """
    This is deprecated! See `print_markdown_and_prompt_copy` on `ExperimentResults`.

    Print the result of `compute_average_runtimes` in markdown table format.
    """
    results = ExperimentResults([list(x) for x in ave_runtimes])

    # Infer integer vs float columns using a heuristic
    has_float = [False] * len(results.rows[0])
    for row in results.rows:
        for i, x in enumerate(row):
            # Multiply epsilon by x to account for float precision
            if abs(x - round(x)) > (0.00001 * x):
                has_float[i] = True

    results.print_markdown_and_prompt_copy(
        [(i, h, 8, 3 if f else 0) for i, (h, f) in enumerate(zip(headers, has_float))]
    )


class _SetupShim:
    def __init__(self, recursion_limit: int | None):
        self.recursion_limit = recursion_limit
    def __call__(self):
        if self.recursion_limit:
            sys.setrecursionlimit(self.recursion_limit)

# The old implementation provided a bunch of type coercion that we no longer provide,
# so these shims are needed to maintain that behavior.

class _RunShim[_T_Out]:
    def __init__(self, fn: Callable[..., _T_Out]):
        self.fn = fn
    def __call__(self, x: tuple):
        return self.fn(*x)

class _PreprocessingShim:
    def __init__(self, fn: Callable | None):
        self.fn = fn if fn else _preprocess_shim_default
    def __call__(self, x):
        if not isinstance(x, list | tuple):
            x = (x,)
        y = self.fn(*x)
        if not isinstance(x, list | tuple):
            y = (y,)
        return y

def _preprocess_shim_default(*x):
    return x

class _PostprocessingShim(Instrument):
    def __init__(self, fn: Callable):
        self.fn = fn
    def __call__(self, f, r):
        def f2(x):
            y = f(x) 
            if not isinstance(x, list | tuple):
                x = (x,)
            self.fn(*x)
            return y
        return f2

def measure_runtime(
    run: Callable[..., _T_Out],
    inputs: list[tuple],
    runtime_scalar: int = 1,
    preprocessing: Callable | None = None,
    postprocessing: Callable | None = None,
    output_group: list[int] | None = None,
    recursion_limit: int | None = None,
    error_message: str = "",
):
    """
    This is deprecated! See the `Experiment` API.
    
    Measure runtime of a process given inputs and write to a JSON file

    :param run: The process to run
    :param inputs: A list of tuples containing all input variations for `run`
    :param runtime_scalar: An integer to multiply your runtime by. Default is 1 (seconds)
    :param preprocessing: A function that takes the current input and returns what will be passed to `run`
    :param postprocessing: A function that takes the return value of `run`
    :param output_group: An ordered list of index numbers that determines what information from an input will be output to the JSON file
    :param recursion_limit: Allows you to raise Python recursion limit if running as a child process
    """
    experiment = Experiment[tuple, tuple, _T_Out](
        _RunShim(run),
        preprocess = _PreprocessingShim(preprocessing),
        setup = _SetupShim(recursion_limit)
    )
    runtime_stage_id = experiment.add_instrument(InstrumentRuntime(float(runtime_scalar)))
    input_stage_id = experiment.add_instrument(instrument_numeric_inputs)
    if postprocessing:
        experiment.add_instrument(_PostprocessingShim(postprocessing))

    # Preprocessing might mess with len(inputs[0]) but this is what the old code did
    selector = [(input_stage_id, i) for i in (range(len(inputs[0])) if output_group is None else output_group)]
    selector.append((runtime_stage_id, 0))
    results = experiment.run(inputs, selector)
    
    output_folder = Path.cwd()
    filename = run.__name__ + "_runtimes.json"
    runtimes_file = os.path.join(output_folder, filename)
    results.legacy_dump(runtimes_file)

def compute_coefficient(filename, big_o, start, end):
    """
    This is deprecated! See the `Experiment` API.
    
    Calculates the constant of proportionality of a curve against
    a data set and displays a bar plot of the resulting ratios.
    """
    results = ExperimentResults.legacy_load(filename)
    results.rows = results.rows[start:end]
    row_len = len(results.rows[0])
    results.display_constant_of_proportionality_report(big_o, list(range(row_len-1)), [row_len-1], ["runtime"])

# TODO: write tests
