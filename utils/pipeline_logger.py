"""
Pipeline Logger - Two-level logging for clean terminal output.

  log(msg)   → always printed (milestones, errors, final summary)
  debug(msg) → only printed when verbose mode is on

Set verbose mode at startup:
    from utils.pipeline_logger import set_verbose
    set_verbose(True)   # show all debug output
    set_verbose(False)  # show only milestones (default)
"""

_verbose: bool = False


def set_verbose(v: bool) -> None:
    """Enable or disable verbose (debug) output."""
    global _verbose
    _verbose = v


def is_verbose() -> bool:
    """Return current verbose setting."""
    return _verbose


def log(msg: str) -> None:
    """Always printed — milestones, errors, and final summary."""
    print(msg)


def debug(msg: str) -> None:
    """Only printed when verbose mode is on."""
    if _verbose:
        print(msg)
