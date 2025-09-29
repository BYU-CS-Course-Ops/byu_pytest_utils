RED = "rgba(255, 99, 71, 0.4)"
GREEN = "rgba(50, 205, 50, 0.4)"
BLUE = "rgba(100, 149, 237, 0.4)"

class StringComparator:
    """Handles string comparison and HTML highlighting."""

    def __init__(self, gap_char: str = '~'):
        self.gap = gap_char

    def compare(self, observed: str, expected: str) -> tuple[str, str]:
        """Return observed and expected strings with HTML span highlighting."""
        obs_html, exp_html = [], []

        for obs_char, exp_char in zip(observed, expected):
            if obs_char == exp_char:
                obs_html.append(obs_char)
                exp_html.append(exp_char)
            elif obs_char == self.gap:
                exp_html.append(self._highlight(exp_char, RED))
            elif exp_char == self.gap:
                obs_html.append(self._highlight(obs_char, GREEN))
            else:
                obs_html.append(self._highlight(obs_char, BLUE))
                exp_html.append(self._highlight(exp_char, BLUE))

        return ''.join(obs_html), ''.join(exp_html)

    @staticmethod
    def _highlight(char: str, color: str) -> str:
        return f'<span style="background-color: {color}">{char}</span>'

