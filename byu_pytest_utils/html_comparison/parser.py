from .models import TestResults

class TestResultParser:
    """Parses raw test result data into TestResults objects."""

    @staticmethod
    def parse(results_dict: dict) -> list[TestResults]:
        """Convert test result dictionary into a list of TestResults."""
        if len(results_dict) != 1:
            raise ValueError("Expected exactly one key in results dictionary.")

        parsed_results = []
        for test_results in results_dict.values():
            for result in test_results:
                parsed_results.append(TestResults(
                    test_name=result.get('name', ''),
                    score=result.get('score', 0),
                    max_score=result.get('max_score', 0),
                    observed=result.get('observed', ''),
                    expected=result.get('expected', ''),
                    passed=result.get('passed', False),
                    output=result.get('output', ''),
                    test_tier=result.get('test_tier', ''),
                    test_priority=result.get('test_priority', 0),
                ))

        return parsed_results

