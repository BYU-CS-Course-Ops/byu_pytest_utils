from .models import TestResults
from .comparator import StringComparator

class TieredTestRenderer:
    """Handles rendering logic for tiered tests."""

    def __init__(self, comparator: StringComparator):
        self.comparator = comparator

    def prepare_comparison_info(self, test_results: list[TestResults]) -> list[tuple]:
        """Organize test results by tier with proper dependency handling."""
        test_order = self.get_tier_order(test_results)
        comparison_info = []
        prior_failed = False

        for test_tier in test_order:
            tier_results = [r for r in test_results if r.test_tier == test_tier]
            max_score = sum(r.max_score for r in tier_results)

            if prior_failed:
                comparison_info.append(
                    self._create_skipped_tier_entry(test_tier, max_score)
                )
            else:
                score = sum(r.score for r in tier_results)
                passed_all = all(r.passed for r in tier_results)
                status = 'passed' if passed_all else 'failed'
                sub_info = [self._build_test_entry(r) for r in tier_results]
                comparison_info.append((test_tier, sub_info, score, max_score, status))
                prior_failed = not passed_all

        return comparison_info

    def _build_test_entry(self, result: TestResults) -> tuple:
        """Build a single test entry with comparison strings."""
        obs, exp = self.comparator.compare(result.observed, result.expected)
        return (result.test_name, obs, exp, result.output, result.score, result.max_score,
                'passed' if result.passed else 'failed')

    @staticmethod
    def _create_skipped_tier_entry(tier: str, max_score: float) -> tuple:
        """Create entry for a skipped tier."""
        sub_info = [(
            f"{tier} Tier",
            "",
            "",
            "Tests for this tier will run when all prerequisite tiers have passed.",
            None,
            None,
            'failed'
        )]
        return tier, sub_info, 0, max_score, 'failed'

    @staticmethod
    def get_tier_order(test_results: list[TestResults]) -> list[str]:
        """Get ordered list of test tiers."""
        return list({
                        r.test_tier: None
                        for r in sorted(test_results, key=lambda x: (x.test_priority, x.test_tier))
                    }.keys())


class SimpleTestRenderer:
    """Handles rendering logic for non-tiered tests."""

    def __init__(self, comparator: StringComparator):
        self.comparator = comparator

    def prepare_comparison_info(self, test_results: list[TestResults]) -> list[tuple]:
        """Prepare flat list of test results."""
        return [self._build_test_entry(r) for r in test_results]

    def _build_test_entry(self, result: TestResults) -> tuple:
        """Build a single test entry with comparison strings."""
        obs, exp = self.comparator.compare(result.observed, result.expected)
        return (result.test_name, obs, exp, result.output, result.score, result.max_score,
                'passed' if result.passed else 'failed')

get_tier_order = TieredTestRenderer.get_tier_order