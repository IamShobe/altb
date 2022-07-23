import os
import abc
import uuid
import shlex
import shutil
import pathlib
import subprocess
from enum import Enum
from contextlib import contextmanager
from typing import Literal, Tuple, Optional, Dict, Union, List, Annotated

import yaml
import typer
import pydantic
from pydantic import BaseModel, BaseSettings, PrivateAttr, StrictBool, StrictStr, Field, BaseConfig
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


class TagKind(str, Enum):
    link = "link"
    command = "command"


class BaseTag(BaseModel, abc.ABC):
    kind: TagKind
    description: Optional[str]
    spec: BaseModel

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash((self.kind, hash(self.spec)))

    def __eq__(self, other):
        return hash(self) == hash(other)


class LinkTagSpec(BaseModel):
    path: pathlib.Path
    is_copy: Optional[StrictBool] = False

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return hash(self) == hash(other)


class LinkTag(BaseTag):
    kind: Literal[TagKind.link] = TagKind.link
    spec: LinkTagSpec


class CommandTagSpec(BaseModel):
    command: str
    working_directory: Optional[pathlib.Path]
    env: Optional[dict[StrictStr, StrictStr]]

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash(self.command)

    def __eq__(self, other):
        return hash(self) == hash(other)


class CommandTag(BaseTag):
    kind: Literal[TagKind.command] = TagKind.command
    spec: CommandTagSpec


TagConfig = Annotated[Union[CommandTag, LinkTag], Field(discriminator="kind")]

TagDict = Dict[str, TagConfig]


class BinaryStruct(BaseModel):
    name: str
    tags: TagDict = {}
    selected: Optional[str] = None

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

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

        if isinstance(selected, LinkTag):
            if destination.exists():
                destination.unlink()

        elif isinstance(selected, CommandTag):
            if destination.exists():
                os.remove(destination)

        self.selected = None

    def delete_tag(self, tag: str):
        pass

    def select_tag(self, tag: str):
        destination = self.destination
        tag_struct = self.tags[tag]

        if isinstance(tag_struct, LinkTag):
            source = tag_struct.spec.path
            destination.symlink_to(source)

        if isinstance(tag_struct, CommandTag):
            with open(destination, 'w') as f:
                f.writelines([
                    "#!/bin/sh\n",
                    f"{PACKAGE_NAME} run {self.name} -- \"$@\""
                ])

            os.chmod(destination, 0o755)

        self.selected = tag

    def run(self, args: List[str]):
        if not self.selected:
            raise RichValueError("app {app_name} doesn't have any selected tag!", app_name=self.name)

        tag_struct = self.tags[self.selected]
        if not isinstance(tag_struct, CommandTag):
            raise RichValueError("tag {tag} of app {app_name} must be of type {tag_type} to be runnable",
                                 tag=self.selected, app_name=self.name, tag_type=tag_struct.kind)

        working_directory = None
        if tag_struct.spec.working_directory:
            if not tag_struct.spec.working_directory.exists():
                raise RichValueError("path '{path}' doesn't exists for command in tag {tag} of app {app_name}",
                                     path=tag_struct.spec.working_directory, tag=self.selected, app_name=self.name)

            working_directory = tag_struct.spec.working_directory

        user_command = shlex.split(tag_struct.spec.command)
        full_command = [*user_command, *args]

        process_env = {**os.environ}
        if tag_struct.spec.env is not None:
            for key, value in tag_struct.spec.env.items():
                process_env[key] = value

        subprocess.call(full_command, cwd=working_directory, env=process_env)

    def assert_valid(self):
        selected_tag = self.selected
        selected_struct = self.tags[selected_tag]
        if isinstance(selected_struct, LinkTag):
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

    class Config(BaseConfig):
        json_encoders = {
            pathlib.Path: str,
            set: list,
        }
        extra = pydantic.Extra.forbid

    def track_command(self, app_name: str, command: str, tag: str = None,
                      description: str = None, working_directory: pathlib.Path = None):
        if working_directory and not working_directory.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=working_directory)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.binaries:
            self.binaries[app_name] = BinaryStruct(name=app_name)

        spec = CommandTagSpec(command=command, working_directory=working_directory)
        self.binaries[app_name][tag] = CommandTag(description=description, spec=spec)

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

        copy_tags = {**self.binaries[app_name].tags}
        for existing_tag, binary_config in copy_tags.items():
            if isinstance(binary_config, LinkTag):
                if binary_config.spec.path == app_path:
                    if not force:
                        raise RichValueError("path '{app_path}' already exist at tag {tag} in {app_name} application! "
                                             "Use -f to force override",
                                             app_path=app_path, tag=existing_tag, app_name=app_name)

                    self.remove(app_name, existing_tag)

        spec = LinkTagSpec(path=app_path, is_copy=should_copy)
        self.binaries[app_name][tag] = LinkTag(description=description, spec=spec)

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

    class Config(BaseSettings.Config):
        env_prefix = f'{PACKAGE_NAME}_'

    _config: AppConfig = PrivateAttr(None)

    def save(self):
        directory = self.config_path.parent
        if not self.config_path.exists():
            os.makedirs(directory, exist_ok=True)

        with self.config_path.open(mode='w') as f:
            yaml.safe_dump(yaml.safe_load(self._config.json(exclude_none=True)), f)

    def load_or_create(self) -> Tuple[AppConfig, bool]:
        if not self.config_path.exists():
            return DEFAULT_CONFIG.copy(), False

        with self.config_path.open() as f:
            content = yaml.safe_load(f)
            return AppConfig(**content), True

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            try:
                self._config, exists_on_disk = self.load_or_create()
                if not exists_on_disk:
                    self.save()

            except pydantic.ValidationError as e:
                raise RichValueError(str(e))

        return self._config


@contextmanager
def pretty_errors():
    try:
        yield

    except RichValueError as e:
        error_console.print(e)
        raise typer.Exit(1)


@contextmanager
def settings_changes(settings: Settings):
    with pretty_errors():
        try:
            yield
            settings.save()

        except ValueError as e:
            error_console.print(str(e))
            raise typer.Exit(1)
