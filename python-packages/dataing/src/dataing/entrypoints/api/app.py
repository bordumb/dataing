"""ASGI app - Community Edition.

Servers load ``dataing.entrypoints.api.app:app``. Importing this module builds that app,
which configures logging and telemetry for the whole process. Code that builds its own
app, such as the Enterprise Edition, imports create_app() from ``factory`` instead, so it
does not build this one as well.
"""

from .factory import create_app

app = create_app()
