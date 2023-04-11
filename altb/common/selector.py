import curses
from contextlib import contextmanager
from typing import Union, List, TypeVar, TypedDict, Tuple, Generic, Set, Generator

from rich.live import Live
from rich.text import Text
from blessed import Terminal

from rich.console import ConsoleRenderable, Console, ConsoleOptions, RenderResult, Group


T = TypeVar("T")


class Entry(TypedDict, Generic[T]):
    key: Union[str, Text]
    value: T


class Selector(ConsoleRenderable, Generic[T]):
    def __init__(self, options: List[Entry]):
        self.options = options
        self.marked_indexes: Set[int] = set()
        self._hovered_index = 0

    def increment(self):
        if self._hovered_index < len(self.options) - 1:
            self._hovered_index += 1

        else:
            self._hovered_index = 0

    def decrement(self):
        if self._hovered_index > 0:
            self._hovered_index -= 1

        else:
            self._hovered_index = len(self.options) - 1

    def select(self):
        element = self._hovered_index
        if element in self.marked_indexes:
            self.marked_indexes.remove(element)

        else:
            self.marked_indexes.add(element)

    @property
    def selections(self) -> List[T]:
        return [self.options[i]['value'] for i in self.marked_indexes]

    def __rich_console__(
            self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        for i, row in enumerate(self.options):
            hovered_char = "➤" if i == self._hovered_index else " "
            hovered_style_fg = "default"
            hovered_style_bg = "default"
            if i == self._hovered_index:
                hovered_style_bg = "default"
                hovered_style_fg = "default"

            if i in self.marked_indexes:
                pass

            hovered_style = f"{hovered_style_fg} on {hovered_style_bg}"
            rendered_row = Text(f"{hovered_char} ", style=hovered_style, end="")
            yield Group(rendered_row, row['key'])


@contextmanager
def run_selector(options: List[Entry[T]], single=True) -> Generator[Tuple[Live, Selector[T]], None, None]:
    term = Terminal()
    selector: Selector[T] = Selector(options)
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
