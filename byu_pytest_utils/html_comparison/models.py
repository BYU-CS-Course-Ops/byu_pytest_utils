from dataclasses import dataclass

@dataclass
class TestResults:
    """Complete test result data."""
    test_name: str
    score: float
    max_score: float
    observed: str
    expected: str
    passed: bool
    output: str = ""
    test_tier: str = ""
    test_priority: int = 0