import re
from pathlib import Path
from typing import Optional
from datetime import datetime
from bs4 import BeautifulSoup
from dataclasses import dataclass
import jinja2 as jj

# Highlight colors
RED = "rgba(255, 99, 71, 0.4)"        # mismatch
GREEN = "rgba(50, 205, 50, 0.4)"      # extra in observed
BLUE = "rgba(100, 149, 237, 0.4)"     # extra in expected


@dataclass
class TestResults:
    test_name: str
    test_set: str
    score: float
    max_score: float
    observed: str
    expected: str
    output: str
    passed: bool


class HTMLRenderer:
    def __init__(self, template_path: Optional[Path] = None):
        self._html_template = template_path or Path(__file__).parent / 'template.html.jinja'

    def render(
        self,
        test_file_name: str,
        test_results: list[TestResults],
        gap: str = '~',
    ) -> str:
        """Render HTML file with test comparison info and optionally open it."""
        if not self._html_template.exists():
            raise FileNotFoundError(f"Template not found at {self._html_template}")

        template = self._html_template.read_text(encoding="utf-8")

        jinja_args = {
            'TEST_NAME': Path(test_file_name).stem.replace('_', ' ').replace('-', ' ').title(),
            'COMPARISON_INFO': [
                (
                    info.test_name.replace('_', ' ').replace('-', ' ').title(),
                    *self._build_comparison_strings(info.observed, info.expected, gap),
                    info.output,
                    info.score,
                    info.max_score,
                    'passed' if info.passed else 'failed',
                )
                for info in test_results
            ],
            'TESTS_PASSED': sum(info.passed for info in test_results),
            'TOTAL_TESTS': len(test_results),
            'TOTAL_SCORE': round(sum(info.score for info in test_results), 1),
            'TOTAL_POSSIBLE_SCORE': sum(info.max_score for info in test_results),
            'TIME': datetime.now().strftime("%B %d, %Y %I:%M %p")
        }

        html_content = jj.Template(template).render(**jinja_args)

        return html_content

    @staticmethod
    def get_comparison_results(html_content) -> list[str]:
        """Extract and return HTML strings of passed and failed test results with inline styles."""

        soup = BeautifulSoup(html_content, 'html.parser')
        results = []


        for container in soup.find_all('div', class_=re.compile(r'\bcomparison-container(-empty)?\b')):
            # Inline styles for .comparison-container
            container['style'] = (
                "display: flex; "
                "flex-wrap: wrap; "
                "justify-content: space-between; "
                "gap: 10px; "
                "margin-bottom: 10px; "
                "padding: 0 10px;"
            )

            # Inline styles for .section and its children
            for section in container.find_all('div', class_='section'):
                section['style'] = "flex: 1 1 300px; min-width: 0;"

                strong = section.find('strong')
                if strong:
                    strong['style'] = "font-size: 1em;"

                content = section.find('div', class_='content')
                if content:
                    content['style'] = (
                        "background: rgb(245, 245, 245); "
                        "padding: 10px; "
                        "border: 1px solid #ddd; "
                        "border-radius: 3px; "
                        "overflow-x: auto;"
                    )

            results.append(str(container))

        return results

    @staticmethod
    def parse_info(results: dict) -> list[TestResults]:
        """Convert test result dictionary into a list of ComparisonInfo."""
        if len(results) != 1:
            raise ValueError("Expected exactly one key in results dictionary.")

        comparison_info = []
        for test_results in results.values():
            for result in test_results:
                comparison_info.append(TestResults(
                    test_name=result.get('name', ''),
                    score=result.get('score', 0),
                    max_score=result.get('max_score', 0),
                    observed=result.get('observed', ''),
                    expected=result.get('expected', ''),
                    passed=result.get('passed', False)
                ))

        return comparison_info

    @staticmethod
    def _build_comparison_strings(obs: str, exp: str, gap: str) -> tuple[str, str]:
        """Return observed and expected strings with HTML span highlighting."""
        observed, expected = '', ''

        for o, e in zip(obs, exp):
            if o == e:
                observed += o
                expected += e
            elif o == gap:
                expected += f'<span style="background-color: {RED}">{e}</span>'
            elif e == gap:
                observed += f'<span style="background-color: {GREEN}">{o}</span>'
            else:
                observed += f'<span style="background-color: {BLUE}">{o}</span>'
                expected += f'<span style="background-color: {BLUE}">{e}</span>'

        return observed, expected
