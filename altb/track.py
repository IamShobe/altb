import pathlib
from typing import Optional

import typer

from altb.common.utils import pretty_errors
from altb.model.settings import Settings
from altb.options import should_copy_option, should_force_option, full_app_name_option
from altb.service import AltbService

track = typer.Typer()


@track.command()
def path(
        ctx: typer.Context,
        app_details=full_app_name_option,
        app_path: pathlib.Path = typer.Argument(..., help='Binary actual path'),
        description: str = typer.Option(None, "-d", "--description", help="Description of the tracked file"),
        should_copy: bool = should_copy_option,
        force: bool = should_force_option,
):
    """Add new tracking of path kind."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details
    with pretty_errors(), AltbService(settings) as service:
        service.track_path(app_name, app_path, tag=tag, description=description, should_copy=should_copy, force=force)


@track.command()
def command(
        ctx: typer.Context,
        app_details=full_app_name_option,
        command_string: str = typer.Argument(..., help='Command to run'),
        description: str = typer.Option(None, "-d", "--description", help="Description of the tracked file"),
        working_directory: Optional[pathlib.Path] = typer.Option(None, '-w', '--working-directory',
                                                                 help="Working directory of running command"),
):
    """Add new tracking of command kind."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details
    with pretty_errors(), AltbService(settings) as service:
        service.track_command(app_name, command_string, tag=tag, description=description,
                              working_directory=working_directory)
