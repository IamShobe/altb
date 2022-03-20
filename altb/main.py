import curses
import pathlib
import sys
from contextlib import contextmanager
from typing import Union, List, Dict, TypeVar, TypedDict, Tuple, Optional, cast

import pkg_resources
import typer
import yaml
from blessed import Terminal
from natsort import natsorted
from rich.console import ConsoleRenderable, Console, ConsoleOptions, RenderResult, Group
from rich.live import Live
from rich.padding import Padding
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

from altb.track import track
from altb.common import console, error_console
from altb.config import Settings, RichText, settings_changes, TagConfig, TagKind, pretty_errors
from altb.constants import TYPE_TO_COLOR, PACKAGE_NAME
from altb.options import app_name_option, is_short_option, is_current_option, all_tags_option, should_force_option, \
    should_copy_option, full_app_name_option

app = typer.Typer()

__version__ = pkg_resources.get_distribution(PACKAGE_NAME).version

T = TypeVar("T")


class Entry(TypedDict):
    key: Union[str, Text]
    value: T


class Selector(ConsoleRenderable):
    def __init__(self, options: List[Entry]):
        self.options = options
        self.marked = set()
        self._hovered = 0

    def increment(self):
        if self._hovered < len(self.options) - 1:
            self._hovered += 1

        else:
            self._hovered = 0

    def decrement(self):
        if self._hovered > 0:
            self._hovered -= 1

        else:
            self._hovered = len(self.options) - 1

    def select(self):
        element = self._hovered
        if element in self.marked:
            self.marked.remove(element)

        else:
            self.marked.add(element)

    @property
    def selections(self) -> List[T]:
        return [self.options[i]['value'] for i in self.marked]

    def __rich_console__(
            self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        for i, row in enumerate(self.options):
            marked_char = "⬢" if i in self.marked else "⬡"
            hovered_char = "⮞" if i == self._hovered else " "
            symbol_style_fg = "default"
            symbol_style_bg = "default"
            text_style_fg = "default"
            text_style_bg = "default"
            hovered_style_fg = "default"
            hovered_style_bg = "default"
            if i == self._hovered:
                hovered_style_bg = symbol_style_bg = text_style_bg = "default"
                hovered_style_fg = symbol_style_fg = text_style_fg = "default"

            if i in self.marked:
                text_style_fg = "green4"
                symbol_style_fg = "green4"

            text_style = f"{text_style_fg} on {text_style_bg}"
            symbol_style = f"{symbol_style_fg} on {symbol_style_bg}"
            hovered_style = f"{hovered_style_fg} on {hovered_style_bg}"
            rendered_row = Text(f"{hovered_char} ", style=hovered_style, end="")
            yield Group(rendered_row, row['key'])


@contextmanager
def run_selector(options: List[Dict[str, T]], single=True) -> List[T]:
    term = Terminal()
    selector = Selector(options)
    with term.cbreak(), term.hidden_cursor():
        with Live(selector, auto_refresh=False) as live:  # update 4 times a second to feel fluid
            try:
                done = False
                while not done:
                    val = term.inkey(timeout=0.5)
                    if val.is_sequence and val.code == curses.KEY_DOWN or \
                            (not val.is_sequence and str(val).lower() == "j") or \
                            (val.code == term.KEY_TAB):
                        selector.increment()

                    elif (val.is_sequence and val.code == curses.KEY_UP) or \
                            (not val.is_sequence and str(val).lower() == "k"):
                        selector.decrement()

                    elif str(val) == " ":
                        selector.select()
                        if single:
                            done = True

                    elif val.is_sequence and val.code == curses.KEY_ENTER:
                        if single:
                            selector.select()
                        done = True

                    live.refresh()

                yield live, selector

            except KeyboardInterrupt:
                raise


@app.command()
def config(ctx: typer.Context, is_json: bool = typer.Option(False, '-j', '--json', help='Output in json format')):
    """Get the config specifications."""
    settings = ctx.ensure_object(Settings)
    to_print = settings.config.json(indent=2)
    if not is_json:
        to_print = yaml.safe_dump(yaml.safe_load(to_print))

    if sys.stdout.isatty():
        console.print(Syntax(to_print, "yaml" if not is_json else "json",
                             background_color="default", word_wrap=True))

    else:
        typer.echo(to_print)


app.add_typer(track, name="track")


@app.command(name="list")
def list_applications(
        ctx: typer.Context,
        app_name: Optional[str] = app_name_option,
        is_short: bool = is_short_option,
        all_tags: bool = all_tags_option,
        current_only: bool = is_current_option,
):
    """List all applications tracked."""
    settings = ctx.ensure_object(Settings)
    if len(settings.config.binaries) == 0:
        error_console.print(f'No binaries currently tracked, please use "{PACKAGE_NAME} track" command to start')
        return

    if app_name is not None and app_name not in settings.config.binaries:
        error_console.print(RichText('app {app_name} doesn\'t exist in config!', app_name=app_name))
        raise typer.Exit(1)

    if app_name is not None and current_only:
        selected_tag = settings.config.binaries[app_name].selected
        if not selected_tag:
            error_console.print(RichText("app {app_name} doesn\'t have selected tag!", app_name=app_name))
            raise typer.Exit(1)

        console.print(Text(selected_tag, style=TYPE_TO_COLOR['tag']))
        return

    app_names = [app_name] if app_name is not None else settings.config.binaries.keys()
    for app_name in app_names:
        tree = Tree(Text(app_name, style=TYPE_TO_COLOR['app_name']))
        selected_tag = settings.config.binaries[app_name].selected
        for tag, value in natsorted(settings.config.binaries[app_name].tags.items(), key=lambda a: a[0]):
            tag_struct = cast(TagConfig, value)
            if not all_tags and tag != selected_tag:
                continue

            group = Group()
            line = Text("* " if tag == selected_tag else "  ", style="bold magenta3") + Text(tag,
                                                                                             style=TYPE_TO_COLOR['tag'])
            if not is_short:
                if tag_struct.kind == TagKind.LINK_TYPE:
                    line += Text(" - ", style="reset") + Text(str(tag_struct.spec.path),
                                                              style=TYPE_TO_COLOR['app_path'])

                elif tag_struct.kind == TagKind.COMMAND_TYPE:
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
    app_name, tag = app_details  # type: str
    if not tag:
        error_console.print(RichText('tag not specified for application {app_name}', app_name=app_name))
        raise typer.Exit(1)

    with settings_changes(settings):
        settings.config.rename_tag(app_name, tag, tag_name)


@app.command()
def describe(
        ctx: typer.Context,
        app_details=full_app_name_option,
        description: str = typer.Option(None, "-d", "--description", help="Description of the tracked file"),
):
    """Add description to a given app's tag."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details  # type: str
    if not tag:
        error_console.print(RichText('tag not specified for application {app_name}', app_name=app_name))
        raise typer.Exit(1)

    if description is None:
        should_continue = Confirm.ask("Description will be deleted, are you sure?", default=False)
        if not should_continue:
            raise typer.Exit(1)

    with settings_changes(settings):
        settings.config.describe_tag(app_name, tag, description)


def get_tag_dynamic(settings: Settings, app_name: str):
    tags: List[Tuple[str, TagConfig]] = \
        natsorted(settings.config.binaries[app_name].tags.items(), key=lambda a: a[0])
    options: List[Entry] = []
    for tag, details in tags:
        if details.kind == TagKind.LINK_TYPE:
            options.append({
                "key": RichText("{tag} - {app_path}", tag=tag, app_path=details.spec.path).text,
                "value": tag,
            })

        elif details.kind == TagKind.COMMAND_TYPE:
            options.append({
                "key": RichText(
                    "{tag} - {command} at {app_path}",
                    tag=tag, command=details.spec.command,
                    app_path=details.spec.working_directory,
                ).text,
                "value": tag,
            })

    with run_selector(options) as (live, selector):
        tag = selector.selections[0]
        live.update(RichText('using tag {tag} for app {app_name}', tag=tag, app_name=app_name))
        return tag


@app.command()
def use(
        ctx: typer.Context,
        app_details: str = full_app_name_option,
):
    """Select which tag to run of a given app."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details  # type: str
    if not tag:
        tag = get_tag_dynamic(settings, app_name)

    with settings_changes(settings):
        settings.config.select(app_name, tag)


@app.command()
def run(
        ctx: typer.Context,
        app_name: str = app_name_option,
        args: Optional[List[str]] = typer.Argument(None)
):
    """Run application with propagated args."""
    if args is None:
        args = []

    settings = ctx.ensure_object(Settings)
    with pretty_errors():
        settings.config.run(app_name, args)


@app.command()
def untrack(
        ctx: typer.Context,
        app_details: str = full_app_name_option,
):
    """Remove tracking of a tag completely."""
    settings = ctx.ensure_object(Settings)
    app_name, tag = app_details  # type: str
    if not tag:
        tag = get_tag_dynamic(settings, app_name)

    with settings_changes(settings):
        settings.config.remove(app_name, tag)


@app.command()
def unlink(
        ctx: typer.Context,
        app_name: str = app_name_option,
):
    """Unset selected tag for a given app."""
    settings = ctx.ensure_object(Settings)
    with settings_changes(settings):
        settings.config.select(app_name, tag=None)


@app.callback(invoke_without_command=True)
def _main(
        ctx: typer.Context,
        version: bool = typer.Option(False, '-v', '--version', help='Show version', is_eager=True),
):
    if version:
        typer.echo(__version__)


def main():
    app()


if __name__ == '__main__':
    main()
