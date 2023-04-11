from contextlib import contextmanager

import typer

from .console import error_console
from .rich import RichValueError


@contextmanager
def pretty_errors():
    try:
        yield

    except RichValueError as e:
        error_console.print(e)
        raise typer.Exit(1)
