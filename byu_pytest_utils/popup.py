_POPUP = False


def set_popup(value: bool):
    """Set whether popups should be used."""
    global _POPUP
    _POPUP = value


def get_popup() -> bool:
    """Return the current POPUP setting."""
    return _POPUP
