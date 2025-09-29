from pathlib import Path
from datetime import datetime
from typing import Optional
import jinja2 as jj

from .models import TestResults
from .comparator import StringComparator
from .renderers import TieredTestRenderer, SimpleTestRenderer

class HTMLRenderer:
    """Main renderer that orchestrates the rendering process."""

    def __init__(self, template_path: Optional[Path] = None, gap_char: str = '~'):
        self.template_path = template_path or Path(__file__).parent / 'template.html.jinja'
        self.comparator = StringComparator(gap_char)
        self.tiered_renderer = TieredTestRenderer(self.comparator)
        self.simple_renderer = SimpleTestRenderer(self.comparator)

    def render(self, test_file_name: str, test_results: list[TestResults]) -> str:
        """Render test results to HTML."""
        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found at {self.template_path}")

        template = self.template_path.read_text(encoding="utf-8")
        test_name = Path(test_file_name).stem
        timestamp = datetime.now().strftime("%B %d, %Y %I:%M %p")

        if self._has_tiers(test_results):
            context = self._build_tiered_context(test_name, test_results, timestamp)
        else:
            context = self._build_simple_context(test_name, test_results, timestamp)

        return jj.Template(template).render(**context)

    def _build_tiered_context(self, test_name: str, test_results: list[TestResults],
                              timestamp: str) -> dict:
        """Build template context for tiered tests."""
        comparison_info = self.tiered_renderer.prepare_comparison_info(test_results)

        return {
            'TEST_TIER': True,
            'TEST_NAME': test_name,
            'COMPARISON_INFO': comparison_info,
            'TESTS_PASSED': sum(1 for *_, status in comparison_info if status == 'passed'),
            'TOTAL_TESTS': len(comparison_info),
            'TOTAL_SCORE': round(sum(score for *_, score, _, _ in comparison_info), 1),
            'TOTAL_POSSIBLE_SCORE': sum(max_score for *_, max_score, _ in comparison_info),
            'TIME': timestamp,
        }

    def _build_simple_context(self, test_name: str, test_results: list[TestResults],
                              timestamp: str) -> dict:
        """Build template context for simple tests."""
        comparison_info = self.simple_renderer.prepare_comparison_info(test_results)

        return {
            'TEST_TIER': False,
            'TEST_NAME': test_name,
            'COMPARISON_INFO': comparison_info,
            'TESTS_PASSED': sum(1 for r in test_results if r.passed),
            'TOTAL_TESTS': len(test_results),
            'TOTAL_SCORE': round(sum(r.score for r in test_results), 1),
            'TOTAL_POSSIBLE_SCORE': sum(r.max_score for r in test_results),
            'TIME': timestamp,
        }

    @staticmethod
    def _has_tiers(test_results: list[TestResults]) -> bool:
        return any(r.test_tier for r in test_results)


def get_css() -> str:
    """Load CSS template."""
    css_path = Path(__file__).parent / 'template.css'
    return css_path.read_text()