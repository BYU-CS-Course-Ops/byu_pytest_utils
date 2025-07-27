import pytest

def baseline(func):
    return pytest.mark.baseline(func)

def core(func):
    return pytest.mark.core(func)

def stretch1(func):
    return pytest.mark.stretch1(func)

def stretch2(func):
    return pytest.mark.stretch2(func)
