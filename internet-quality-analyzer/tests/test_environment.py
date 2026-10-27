"""
Environment verification test.
Ensures Python version meets requirements and key dependencies are properly installed.
"""

import sys
import platform

def test_python_version():
    """Verify Python version is 3.11 or newer."""
    assert sys.version_info >= (3, 11), f"Python 3.11+ required, got {sys.version}"

def test_flask_installed():
    """Verify Flask is installed and importable."""
    import importlib.metadata
    assert importlib.metadata.version("flask") is not None

def test_dnspython_installed():
    """Verify dnspython is installed and importable."""
    import dns.resolver
    assert dns.__version__ is not None

def test_system_platform():
    """Log platform details for diagnostic validation."""
    system = platform.system()
    assert system in ("Windows", "Linux", "Darwin"), f"Unsupported platform: {system}"
