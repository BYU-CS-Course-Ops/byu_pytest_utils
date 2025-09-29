import re
from bs4 import BeautifulSoup

def get_comparison_results(html_content: str) -> list[str]:
    """Extract HTML strings of passed and failed test results."""
    flattened = re.sub(r'>\s*\n\s*<', '><', html_content).strip()
    soup = BeautifulSoup(flattened, 'html.parser')
    results = []

    for div in soup.find_all('div', class_=['test-result-failed', 'test-result-passed']):
        for header in div.find_all(class_=['result-header', 'result-subheader']):
            header.decompose()
        results.append(str(div))

    return results

