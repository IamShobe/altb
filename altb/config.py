import os
import pathlib
import uuid
from contextlib import contextmanager
from typing import Tuple, Optional, Dict, Set

import typer
import yaml
from pydantic import BaseModel, BaseSettings, PrivateAttr
from rich.console import ConsoleOptions, RenderResult, Console, ConsoleRenderable

from altb.constants import CONFIG_FILE, TYPE_TO_COLOR, PACKAGE_NAME
from altb.common import error_console


class RichText(ConsoleRenderable):
    def __init__(self, msg, **kwargs):
        self.msg = msg
        self.kwargs = kwargs

    @property
    def text(self):
        new_kwargs = {}
        for kwarg, value in self.kwargs.items():
            if kwarg in TYPE_TO_COLOR:
                color = TYPE_TO_COLOR[kwarg]
                new_kwargs[kwarg] = f"[{color}]{value}[/{color}]"

            else:
                new_kwargs[kwarg] = value

        return self.msg.format(**new_kwargs)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions,
    ) -> RenderResult:
        yield self.text


class RichValueError(ValueError):
    def __init__(self, msg, **kwargs):
        self.kwargs = kwargs
        self.msg = msg
        super(RichValueError, self).__init__(msg.format(**kwargs))

    def __rich_console__(
            self, console: Console, options: ConsoleOptions,
    ) -> RenderResult:
        yield RichText(self.msg, **self.kwargs)


class TagConfig(BaseModel):
    path: pathlib.Path
    description: Optional[str]

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return hash(self) == hash(other)


TagDict = Dict[str, TagConfig]


class BinaryStruct(BaseModel):
    tags: TagDict = {}
    selected: Optional[str] = None

    def __getitem__(self, item):
        return self.tags[item]

    def __setitem__(self, key, value):
        self.tags[key] = value

    def __delitem__(self, key):
        del self.tags[key]


class AppConfig(BaseModel):
    binaries: Dict[str, BinaryStruct] = {}

    class Config:
        json_encoders = {
            pathlib.Path: str,
            set: list,
        }

    def track(self, app_name: str, app_path: pathlib.Path, tag: str = None, description: str = None):
        if not app_path.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=app_path)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.binaries:
            self.binaries[app_name] = BinaryStruct()

        for existing_tag, binary_config in self.binaries[app_name].tags.items():
            if binary_config.path == app_path:
                raise RichValueError("path '{app_path}' already exist at tag {tag} in {app_name} application!",
                                     app_path=app_path, tag=existing_tag, app_name=app_name)

        self.binaries[app_name][tag] = TagConfig(path=app_path, tag=tag, description=description)

    def rename_tag(self, app_name: str, tag: str, new_tag: str):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        obj = self.binaries[app_name][tag]
        self.binaries[app_name][new_tag] = obj
        self.remove(app_name, tag, new_selected=new_tag)  # remove old tag

    def describe_tag(self, app_name: str, tag: str, description: str):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        obj = self.binaries[app_name][tag]
        obj.description = description

    def assert_link_valid(self, app_name):
        destination = pathlib.Path.home() / '.local' / 'bin' / app_name
        if destination.exists():
            selected_tag = self.binaries[app_name].selected
            selected_struct = self.binaries[app_name][selected_tag]
            if destination.is_symlink():
                actual_link = destination.readlink()
                if selected_struct.path != actual_link:
                    raise RichValueError("DRIFT DETECTED! {app_path} is linked to a different binary, "
                                         "please remove existing link to continue using this link",
                                         app_path=str(destination))

            else:
                raise RichValueError("path {app_path} isn't a symlink and probably not managed by {package_name}",
                                     app_path=str(destination), package_name=PACKAGE_NAME)

    def select(self, app_name: str, tag: Optional[str]):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag is not None and tag not in self.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        destination = pathlib.Path.home() / '.local' / 'bin' / app_name
        self.assert_link_valid(app_name)
        if destination.exists():
            destination.unlink()

        if tag is not None:
            source = self.binaries[app_name].tags[tag].path
            destination.symlink_to(source)

        self.binaries[app_name].selected = tag

    def remove(self, app_name: str, tag: str, new_selected: Optional[str] = None):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        selected_tag = self.binaries[app_name].selected
        if selected_tag == tag:
            self.select(app_name, tag=new_selected)  # clear selected tag

        del self.binaries[app_name][tag]


DEFAULT_CONFIG: AppConfig = AppConfig()


class Settings(BaseSettings):
    config_path: pathlib.Path = CONFIG_FILE
    class Config:
        env_prefix = f'{PACKAGE_NAME}_'

    _config: AppConfig = PrivateAttr(None)

    def save(self):
        directory = self.config_path.parent
        if not self.config_path.exists():
            os.makedirs(directory, exist_ok=True)

        with self.config_path.open(mode='w') as f:
            yaml.safe_dump(yaml.safe_load(self._config.json()), f)

    def load_or_create(self) -> Tuple[AppConfig, bool]:
        if not self.config_path.exists():
            return DEFAULT_CONFIG, True

        with self.config_path.open() as f:
            return AppConfig(**yaml.safe_load(f)), False

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config, should_create_new = self.load_or_create()
            if should_create_new:
                self.save()

        return self._config


@contextmanager
def settings_changes(settings):
    try:
        yield
        settings.save()
    except RichValueError as e:
        error_console.print(e)
        raise typer.Exit(1)

    except ValueError as e:
        error_console.print(str(e))
        raise typer.Exit(1)