import enum
import os
import pathlib
import shutil
import stat
import subprocess
import uuid
from contextlib import contextmanager
from typing import Tuple, Optional, Dict, Union, List

import typer
import yaml
from pydantic import BaseModel, BaseSettings, PrivateAttr
from rich.console import ConsoleOptions, RenderResult, Console, ConsoleRenderable

from altb.constants import CONFIG_FILE, TYPE_TO_COLOR, PACKAGE_NAME, VERSIONS_DIRECTORY
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


class LinkTag(BaseModel):
    path: pathlib.Path
    is_copy: Optional[bool] = False

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return hash(self) == hash(other)

    def remove(self):
        pass


class CommandTag(BaseModel):
    command: str
    working_directory: Optional[pathlib.Path]

    def __hash__(self):
        return hash(self.command)

    def __eq__(self, other):
        return hash(self) == hash(other)


class TagKind(enum.Enum):
    LINK_TYPE = 'link'
    COMMAND_TYPE = 'command'


class TagConfig(BaseModel):
    kind: TagKind
    description: Optional[str]
    spec: Union[LinkTag, CommandTag]

    def __hash__(self):
        return hash((self.kind, hash(self.spec)))

    def __eq__(self, other):
        return hash(self) == hash(other)


TagDict = Dict[str, TagConfig]


class BinaryStruct(BaseModel):
    name: str
    tags: TagDict = {}
    selected: Optional[str] = None

    def __getitem__(self, item):
        return self.tags[item]

    def __setitem__(self, key, value):
        self.tags[key] = value

    def __delitem__(self, key):
        del self.tags[key]

    @property
    def destination(self):
        return pathlib.Path.home() / '.local' / 'bin' / self.name

    def unselect_current_tag(self):
        selected = self.tags[self.selected]
        destination = self.destination

        if selected.kind == TagKind.LINK_TYPE:
            if destination.exists():
                destination.unlink()

        elif selected.kind == TagKind.COMMAND_TYPE:
            if destination.exists():
                os.remove(destination)

        self.selected = None

    def delete_tag(self, tag: str):
        pass

    def select_tag(self, tag: str):
        destination = self.destination
        tag_struct = self.tags[tag]

        if tag_struct.kind == TagKind.LINK_TYPE:
            source = tag_struct.spec.path
            destination.symlink_to(source)

        if tag_struct.kind == TagKind.COMMAND_TYPE:
            with open(destination, 'w') as f:
                f.writelines([
                    "#!/bin/sh\n",
                    f"{PACKAGE_NAME} run {self.name} \"$@\""
                ])

            os.chmod(destination, 0o755)

        self.selected = tag

    def run(self, args: List[str]):
        if not self.selected:
            raise RichValueError("app {app_name} doesn't have any selected tag!", app_name=self.name)

        tag_struct = self.tags[self.selected]
        if not tag_struct.kind == TagKind.COMMAND_TYPE:
            raise RichValueError("tag {tag} of app {app_name} must be of type {tag_type} to be runnable",
                                 tag=self.selected, app_name=self.name, tag_type=TagKind.COMMAND_TYPE.value)

        args_as_string = " ".join(args)
        if tag_struct.spec.working_directory:
            if not tag_struct.spec.working_directory.exists():
                raise RichValueError("path '{path}' doesn't exists for command in tag {tag} of app {app_name}",
                                     path=tag_struct.spec.working_directory, tag=self.selected, app_name=self.name)

            os.chdir(tag_struct.spec.working_directory)

        os.system(f"{tag_struct.spec.command} {args_as_string}")

    def assert_valid(self):
        selected_tag = self.selected
        selected_struct = self.tags[selected_tag]
        if selected_struct.kind == TagKind.LINK_TYPE:
            if self.destination.is_symlink():
                actual_link = self.destination.readlink()
                if selected_struct.spec.path != actual_link:
                    raise RichValueError("DRIFT DETECTED! {app_path} is linked to a different binary, "
                                         "please remove existing link to continue using this link",
                                         app_path=str(self.destination))

            else:
                raise RichValueError("path {app_path} isn't a symlink and probably not managed by {package_name}",
                                     app_path=str(self.destination), package_name=PACKAGE_NAME)


class AppConfig(BaseModel):
    binaries: Dict[str, BinaryStruct] = {}

    class Config:
        json_encoders = {
            pathlib.Path: str,
            set: list,
        }

    def track_command(self, app_name: str, command: str, tag: str = None,
                      description: str = None, working_directory: pathlib.Path = None):
        if working_directory and not working_directory.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=working_directory)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.binaries:
            self.binaries[app_name] = BinaryStruct(name=app_name)

        spec = CommandTag(command=command, working_directory=working_directory)
        self.binaries[app_name][tag] = TagConfig(tag=tag, description=description, kind=TagKind.COMMAND_TYPE, spec=spec)

    def track_path(self, app_name: str, app_path: pathlib.Path, tag: str = None,
                   description: str = None, should_copy: bool = False, force: bool = False):
        if not app_path.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=app_path)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.binaries:
            self.binaries[app_name] = BinaryStruct(name=app_name)

        if should_copy:
            version_directory = VERSIONS_DIRECTORY / app_name
            os.makedirs(version_directory, exist_ok=True)
            original_app_path = app_path
            app_path = version_directory / f'{app_name}_{tag}'
            if app_path.exists() and not force:
                raise RichValueError(f"Can not copy file to path - '{app_path}': already exists. "
                                     f"Please delete it manually or use -f flag")
            shutil.copy(original_app_path, app_path)

        for existing_tag, binary_config in self.binaries[app_name].tags.items():
            if binary_config.kind == TagKind.LINK_TYPE:
                if binary_config.spec.path == app_path:
                    if not force:
                        raise RichValueError("path '{app_path}' already exist at tag {tag} in {app_name} application! "
                                             "Use -f to force override",
                                             app_path=app_path, tag=existing_tag, app_name=app_name)

                    self.remove(app_name, existing_tag)

        spec = LinkTag(path=app_path, is_copy=should_copy)
        self.binaries[app_name][tag] = TagConfig(tag=tag, description=description, kind=TagKind.LINK_TYPE, spec=spec)

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

    def select(self, app_name: str, tag: Optional[str]):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag is not None and tag not in self.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        app = self.binaries[app_name]
        if app.selected:
            app.assert_valid()
            app.unselect_current_tag()

        if tag is not None:
            app.select_tag(tag)

    def run(self, app_name: str, args: List[str]):
        if app_name not in self.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        app = self.binaries[app_name]
        app.run(args)

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
def pretty_errors():
    try:
        yield

    except RichValueError as e:
        error_console.print(e)
        raise typer.Exit(1)


@contextmanager
def settings_changes(settings):
    with pretty_errors():
        try:
            yield
            settings.save()

        except ValueError as e:
            error_console.print(str(e))
            raise typer.Exit(1)
