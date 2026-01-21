"""JupyterLab extension for Dataing data quality investigation."""

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.1.0"


def _jupyter_labextension_paths():
    """Return the JupyterLab extension path."""
    return [{"src": "labextension", "dest": "@dataing/jupyterlab-dataing"}]
