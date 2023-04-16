import sys
import json
from typing import List, Optional, cast

import typer
import yaml
from rich.tree import Tree
from rich.text import Text
from natsort import natsorted
from rich.padding import Padding
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.console import Group

from altb import version_file
from altb.common.console import error_console, console
from altb.common.rich import RichText
from altb.common.selector import Entry, run_selector
from altb.common.utils import pretty_errors
from altb.model.config import AppConfig
from altb.model.settings import Settings
from altb.model.tags import TagConfig, LinkTag, CommandTag
from altb.service import AltbService
from altb.track import track
from altb.common.constants import TYPE_TO_COLOR, PACKAGE_NAME
from altb.options import (app_name_option,
                          is_short_option,
                          is_current_option,
                          all_tags_option,
                          full_app_name_option, should_force_option)

app = typer.Typer(pretty_exceptions_enable=False)

app.add_typer(track, name="track")


@app.command()
def config(ctx: typer.Context, is_json: bool = typer.Option(False, '-j', '--json', help='Output in json format')):
    """Get the config specifications."""
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    to_print = service.config.json(indent=2)
    if not is_json:
        to_print = yaml.safe_dump(yaml.safe_load(to_print))

    if sys.stdout.isatty():
        console.print(Syntax(to_print, "yaml" if not is_json else "json",
                             background_color="default", word_wrap=True))

    else:
        typer.echo(to_print)


@app.command(name="list")
def list_applications(
        ctx: typer.Context,
        app_name: str = app_name_option,
        is_short: bool = is_short_option,
        all_tags: bool = all_tags_option,
        current_only: bool = is_current_option,
):
    """List all applications tracked."""
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)

    if len(service.config.binaries) == 0:
        error_console.print(f'No binaries currently tracked, please use "{PACKAGE_NAME} track" command to start')
        return

    if app_name is not None and app_name not in service.config.binaries:
        error_console.print(RichText('app {app_name} doesn\'t exist in config!', app_name=app_name))
        raise typer.Exit(1)

    if app_name is not None and current_only:
        selected_tag = service.config.binaries[app_name].selected
        if not selected_tag:
            error_console.print(RichText("app {app_name} doesn\'t have selected tag!", app_name=app_name))
            raise typer.Exit(1)

        console.print(Text(selected_tag, style=TYPE_TO_COLOR['tag']))
        return

    app_names = [app_name] if app_name is not None else service.config.binaries.keys()
    for app_name in app_names:
        tree = Tree(Text(app_name, style=TYPE_TO_COLOR['app_name']))
        selected_tag = service.config.binaries[app_name].selected
        for tag, value in natsorted(service.config.binaries[app_name].tags.items(), key=lambda a: a[0]):
            tag_struct = cast(TagConfig, value)
            if not all_tags and tag != selected_tag:
                continue

            group = Group()
            line = Text("* " if tag == selected_tag else "  ", style="bold magenta3") + Text(tag,
                                                                                             style=TYPE_TO_COLOR['tag'])
            if not is_short:
                if isinstance(tag_struct, LinkTag):
                    line += Text(" - ", style="reset") + Text(str(tag_struct.spec.path),
                                                              style=TYPE_TO_COLOR['app_path'])

                elif isinstance(tag_struct, CommandTag):
                    line += (
                            Text(" - ", style="reset") +
                            Text(str(tag_struct.spec.command), style=TYPE_TO_COLOR['command']) +
                            Text(' at ', style="reset") +
                            Text(str(tag_struct.spec.working_directory), style=TYPE_TO_COLOR['app_path'])
                    )

            group.renderables.append(line)
            if tag_struct.description and not is_short:
                group.renderables.append(Padding(Text(tag_struct.description), pad=(0, 0, 0, 4), expand=False))

            tree.add(group)
        console.print(tree)


@app.command()
def rename_tag(
        ctx: typer.Context,
        app_details=full_app_name_option,
        tag_name: str = typer.Argument(..., help="New tag name to change to")
):
    """Rename tag."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details
    if not tag:
        error_console.print(RichText('tag not specified for application {app_name}', app_name=app_name))
        raise typer.Exit(1)

    with pretty_errors(), AltbService(settings) as service:
        service.rename_tag(app_name, tag, tag_name)


@app.command()
def describe(
        ctx: typer.Context,
        app_details=full_app_name_option,
        description: str = typer.Option(None, "-d", "--description", help="Description of the tracked file"),
):
    """Add description to a given app's tag."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details
    if not tag:
        error_console.print(RichText('tag not specified for application {app_name}', app_name=app_name))
        raise typer.Exit(1)

    if description is None:
        should_continue = Confirm.ask("Description will be deleted, are you sure?", default=False)
        if not should_continue:
            raise typer.Exit(1)

    with pretty_errors(), AltbService(settings) as service:
        service.describe_tag(app_name, tag, description)


def get_app_dynamic(app_config: AppConfig):
    apps: List[str] = natsorted(app_config.binaries.keys())
    options: List[Entry] = []
    for app_name in apps:
        options.append({
            "key": RichText("{app_name}", app_name=app_name).text,
            "value": app_name,
        })

    with run_selector(options) as context:
        live, selector = context
        app_name = selector.selections[0]
        live.update(RichText('select tag for {app_name}:', app_name=app_name))
        return app_name


def get_tag_dynamic(app_config: AppConfig, app_name: str):
    tags = natsorted(app_config.binaries[app_name].tags.items(), key=lambda a: a[0])
    options: List[Entry] = []
    for tag, details in tags:
        if isinstance(details, LinkTag):
            options.append({
                "key": RichText("{tag} - {app_path}", tag=tag, app_path=details.spec.path).text,
                "value": tag,
            })

        elif isinstance(details, CommandTag):
            options.append({
                "key": RichText(
                    "{tag} - {command} at {app_path}",
                    tag=tag, command=details.spec.command,
                    app_path=details.spec.working_directory,
                ).text,
                "value": tag,
            })

    with run_selector(options) as context:
        live, selector = context
        tag = selector.selections[0]
        return tag


@app.command()
def use(
        ctx: typer.Context,
        app_details=full_app_name_option,
        force: bool = should_force_option,
):
    """Select which tag to run of a given app."""
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    app_name, tag = app_details
    if not tag:
        tag = get_tag_dynamic(service.config, app_name)

    console.print(RichText('using tag {tag} for app {app_name}', tag=tag, app_name=app_name))
    with pretty_errors(), AltbService(settings) as service:
        service.select(app_name, tag, force=force)


@app.command()
def run(
        ctx: typer.Context,
        app_name=app_name_option,
        args: Optional[List[str]] = typer.Argument(None)
):
    """Run application with propagated args."""
    if args is None:
        args = []

    settings = ctx.ensure_object(Settings)
    with pretty_errors(), AltbService(settings) as service:
        service.run(app_name, args)


@app.command()
def untrack(
        ctx: typer.Context,
        app_details=full_app_name_option,
):
    """Remove tracking of a tag completely."""
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    app_name, tag = app_details
    if not tag:
        tag = get_tag_dynamic(service.config, app_name)

    with pretty_errors(), AltbService(settings) as service:
        service.remove(app_name, tag)


@app.command()
def unlink(
        ctx: typer.Context,
        app_name=app_name_option,
):
    """Unset selected tag for a given app."""
    settings = ctx.ensure_object(Settings)
    with pretty_errors(), AltbService(settings) as service:
        service.select(app_name, tag=None)


@app.command()
def schema(
        ctx: typer.Context,
        model: Optional[str] = typer.Argument(None),
        dump_all: bool = typer.Option(False, '-a', '--all', help='Dump all scheme')
):
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    schema = service.config.schema()

    if model is not None:
        if model not in schema['definitions']:
            error_console.print(RichText('model `{model}` does not exists', model=model))
            raise typer.Exit(1)

        console.print(Syntax(json.dumps(schema['definitions'][model], indent=2), "json",
                             background_color="default", word_wrap=True))

    else:
        if not dump_all:
            del schema['definitions']

        console.print(Syntax(json.dumps(schema, indent=2), "json",
                             background_color="default", word_wrap=True))


@app.callback(invoke_without_command=True)
def _main(
        ctx: typer.Context,
        version: Optional[bool] = typer.Option(None, '-v', '--version', help='Show version', is_eager=True),
):
    if version is not None and version:
        typer.echo(version_file.version)
        raise typer.Exit()

    if ctx.invoked_subcommand is not None:
        return

    # if no subcommand is specified, use the default one
    settings = ctx.ensure_object(Settings)
    service = AltbService(settings)
    app_name = get_app_dynamic(service.config)
    ctx.invoke(use, ctx=ctx, app_details=(app_name, None))


def main():
    app()


if __name__ == '__main__':
    main()
