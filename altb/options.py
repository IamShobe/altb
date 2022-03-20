import re

import typer

from altb.common import error_console
from altb.config import Settings, TagKind


app_name_regex = re.compile(r'(?P<app_name>\w+)(?:@(?P<tag>.+))?')


def complete_app_name(ctx: typer.Context, incomplete: str):
    settings = ctx.ensure_object(Settings)
    for app_name in settings.config.binaries:
        if incomplete in app_name:
            yield app_name


def parse_app_name(ctx: typer.Context, full_app_name: str):
    match = app_name_regex.match(full_app_name)
    if not match:
        error_console.print('App name must be in format <app_name>[@<tag_name>] - example: "python@3.9.8" or "python"')
        raise typer.Exit(1)

    return match.group('app_name'), match.group('tag')


def complete_full_app_name(ctx: typer.Context, incomplete: str):
    settings = ctx.ensure_object(Settings)
    app_names = list(complete_app_name(ctx, incomplete))
    if "@" not in incomplete and len(app_names) > 1:
        yield from app_names

    else:
        for key, binary_struct in settings.config.binaries.items():
            yield key
            for tag, tag_struct in binary_struct.tags.items():
                full_name = f"{key}@{tag}"
                if incomplete in full_name:
                    if tag_struct.kind == TagKind.LINK_TYPE:
                        yield full_name, str(tag_struct.spec.path)

                    elif tag_struct.kind == TagKind.COMMAND_TYPE:
                        yield full_name, f"{tag_struct.spec.command} at {tag_struct.spec.working_directory}"


full_app_name_option = typer.Argument(...,
                                      help="Binary application name - <app_name>[@<tag_name>] - example: python@3.9.8",
                                      callback=parse_app_name, autocompletion=complete_full_app_name)

app_name_option = typer.Argument(None, help="Binary application name - <app_name> - example: python",
                                 autocompletion=complete_app_name)
is_short_option = typer.Option(False, '-1', '-s', '--short', help="Print short version")
is_current_option = typer.Option(False, '-t', '--current-tag', help="Print current tag only")
all_tags_option = typer.Option(False, '-a', '--all', help="Print all tags")
should_force_option = typer.Option(False, '-f', '--force', help="Force operation")
should_copy_option = typer.Option(False, '-c', '--copy', help="Copy file to versions directory - (mainly for binaries)")
