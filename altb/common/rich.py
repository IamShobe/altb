from rich.console import ConsoleRenderable, Console, ConsoleOptions, RenderResult

from altb.common.constants import TYPE_TO_COLOR


class RichText(ConsoleRenderable):
    def __init__(self, msg, **kwargs):
        self.msg = msg
        self.kwargs = kwargs

    @property
    def text(self):
        new_kwargs = {}
        for kwarg, value in self.kwargs.items():
            if kwarg in TYPE_TO_COLOR:
                color = TYPE_TO_COLOR[kwarg]  # type: ignore
                new_kwargs[kwarg] = f"[{color}]{value}[/{color}]"

            else:
                new_kwargs[kwarg] = value

        return self.msg.format(**new_kwargs)

    def __rich_console__(
            self, console: Console, options: ConsoleOptions,
    ) -> RenderResult:
        yield self.text


class RichValueError(ValueError, ConsoleRenderable):
    def __init__(self, msg, **kwargs):
        self.kwargs = kwargs
        self.msg = msg
        super(RichValueError, self).__init__(msg.format(**kwargs))

    def __rich_console__(
            self, console: Console, options: ConsoleOptions,
    ) -> RenderResult:
        yield RichText(self.msg, **self.kwargs)

