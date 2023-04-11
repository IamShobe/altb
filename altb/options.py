import re
from typing import Optional

import typer

from altb.common.console import error_console
from altb.model.settings import Settings
from altb.model.tags import LinkTag, CommandTag
from altb.service import AltbService

app_name_regex = re.compile(r'(?P<app_name>[\w\-_]+)(?:@(?P<tag>.+))?')


def complete_app_name(ctx: typer.Context, incomplete: str):
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    for app_name in service.config.binaries:
        if incomplete in app_name:
            yield app_name


def parse_app_name(ctx: typer.Context, full_app_name: str) -> tuple[str, str]:
    match = app_name_regex.match(full_app_name)
    if not match:
        error_console.print('App name must be in format <app_name>[@<tag_name>] - example: "python@3.9.8" or "python"')
        raise typer.Exit(1)

    return match.group('app_name'), match.group('tag')


def complete_full_app_name(ctx: typer.Context, incomplete: str):
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    app_names = list(complete_app_name(ctx, incomplete))
    if "@" not in incomplete and len(app_names) > 1:
        yield from app_names

    else:
        for key, binary_struct in service.config.binaries.items():
            yield key
            for tag, tag_struct in binary_struct.tags.items():
                full_name = f"{key}@{tag}"
                if incomplete in full_name:
                    if isinstance(tag_struct, LinkTag):
                        yield full_name, str(tag_struct.spec.path)

                    elif isinstance(tag_struct, CommandTag):
                        yield full_name, f"{tag_struct.spec.command} at {tag_struct.spec.working_directory}"


full_app_name_option: tuple[str, str] = typer.Argument(
    ...,
    help="Binary application name - <app_name>[@<tag_name>] - example: python@3.9.8",
    callback=parse_app_name, autocompletion=complete_full_app_name)

app_name_option: Optional[str] = typer.Argument(None, help="Binary application name - <app_name> - example: python",
                                                autocompletion=complete_app_name)
is_short_option: bool = typer.Option(False, '-1', '-s', '--short', help="Print short version")
is_current_option: bool = typer.Option(False, '-t', '--current-tag', help="Print current tag only")
all_tags_option: bool = typer.Option(False, '-a', '--all', help="Print all tags")
should_force_option: bool = typer.Option(False, '-f', '--force', help="Force operation")
should_copy_option: bool = typer.Option(False, '-c', '--copy',
                                        help="Copy file to versions directory - (mainly for binaries)")
