import re


def aggregate_tier_scores(tier_name: str, test_results: list) -> tuple[dict, bool]:
    """
    Calculate total scores for a test tier.

    Returns: (test_dict, all_passed)
    """
    test_dict = {
        'name': tier_name,
        'output': '',
        'output_format': 'html',
        'score': 0,
        'max_score': 0,
        'visibility': 'visible',
        'status': 'passed'
    }

    all_passed = True
    for result in test_results:
        if result.test_tier == tier_name:
            test_dict['max_score'] += result.max_score
            if result.passed:
                test_dict['score'] += result.score
            else:
                all_passed = False

    if not all_passed:
        test_dict['status'] = 'failed'

    return test_dict, all_passed


def format_tiered_tests(test_results: list, html_results: list[str]) -> dict:
    """Format tiered tests with dependency handling."""
    tier_order = list({
                          r.test_tier: None
                          for r in sorted(test_results, key=lambda x: (x.test_priority, x.test_tier))
                      }.keys())

    tests = []
    prior_failed = False
    html_iter = iter(html_results)

    for tier_name in tier_order:
        test_dict, passed = aggregate_tier_scores(tier_name, test_results)
        test_dict['output'] = next(html_iter)

        # Handle tier dependencies
        if prior_failed:
            test_dict['score'] = 0
            test_dict['status'] = 'failed'
        elif not passed:
            prior_failed = True

        tests.append(test_dict)

    return {'tests': tests}


def format_simple_tests(test_results: list, html_results: list[str]) -> dict:
    """Format non-tiered tests."""
    tests = [
        {
            'name': result.test_name,
            'output': html,
            'output_format': 'html',
            'score': round(result.score, 3),
            'max_score': round(result.max_score, 3),
            'visibility': 'visible',
            'status': 'passed' if result.passed else 'failed'
        }
        for result, html in zip(test_results, html_results)
    ]

    return {'tests': tests}


def format_gradescope_results(test_results: list, html_results: list[str]) -> dict:
    """
    Convert test results to Gradescope JSON format.

    :param test_results: List of TestResults objects
    :param html_results: List of HTML strings for each test/tier
    :return: Dictionary in Gradescope-compatible format
    """
    has_tiers = bool(test_results and getattr(test_results[0], 'test_tier', None))

    if has_tiers:
        return format_tiered_tests(test_results, html_results)
    else:
        return format_simple_tests(test_results, html_results)


def parse_css(css: str) -> dict[str, str]:
    """Extract CSS rules into a dictionary mapping selectors to styles."""
    if not css.strip():
        return {}

    rules = {}
    for match in re.finditer(r'([.#]?[\w-]+)\s*\{\s*([^}]+)\s*\}', css):
        selector = match.group(1).strip()
        declarations = match.group(2).strip()
        rules[selector] = declarations

    return rules


def inline_styles(html: str, css_rules: dict[str, str]) -> str:
    """Apply CSS rules as inline styles to HTML."""
    for selector, style in css_rules.items():
        if selector.startswith('.'):
            class_name = selector[1:]
            pattern = f'(<[^>]*class=["\'][^"\']*{re.escape(class_name)}[^"\']*["\'][^>]*?)>'
            replacement = f'\\1 style="{style}">'
            html = re.sub(pattern, replacement, html)

        elif selector.startswith('#'):
            id_name = selector[1:]
            pattern = f'(<[^>]*id=["\']?{re.escape(id_name)}["\']?[^>]*?)>'
            replacement = f'\\1 style="{style}">'
            html = re.sub(pattern, replacement, html)

    return html


def inline_css(gradescope_json: dict, css: str) -> dict:
    """
    Inline CSS styles into all test outputs in Gradescope JSON.

    :param gradescope_json: Gradescope results dictionary
    :param css: CSS string to inline
    :return: Modified dictionary with inlined styles
    """
    css_rules = parse_css(css)

    if not css_rules:
        return gradescope_json

    for test in gradescope_json.get('tests', []):
        if test.get('output'):
            test['output'] = inline_styles(test['output'], css_rules)

    return gradescope_json