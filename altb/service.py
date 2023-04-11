import os
import pathlib
import shlex
import shutil
import subprocess
import uuid
from typing import Optional, List, ContextManager

import pydantic
import yaml

from altb.common.constants import PACKAGE_NAME
from altb.common.rich import RichValueError
from altb.model.config import AppConfig, BinaryStruct
from altb.model.settings import Settings
from altb.model.tags import CommandTagSpec, CommandTag, LinkTag, LinkTagSpec


class AltbService(ContextManager):
    def __init__(self, settings: Settings):
        self.settings = settings
        self._config = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()

    def save(self):
        directory = self.settings.config_resolved_path.parent
        if not self.settings.config_resolved_path.exists():
            os.makedirs(directory, exist_ok=True)

        with self.settings.config_resolved_path.open(mode='w') as f:
            yaml.safe_dump(yaml.safe_load(self._config.json(exclude_none=True)), f)

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            try:
                self._config, exists_on_disk = self._load_config()
                if not exists_on_disk:
                    self.save()

            except pydantic.ValidationError as e:
                raise RichValueError(str(e))

        assert self._config is not None
        return self._config

    def _load_config(self):
        if not self.settings.config_resolved_path.exists():
            return AppConfig(), False

        with self.settings.config_resolved_path.open() as f:
            content = yaml.safe_load(f)
            return AppConfig(**content), True

    # methods for managing binaries
    def track_command(self, app_name: str, command: str, tag: Optional[str] = None,
                      description: Optional[str] = None, working_directory: Optional[pathlib.Path] = None):
        if working_directory and not working_directory.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=working_directory)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.config.binaries:
            self.config.binaries[app_name] = BinaryStruct(name=app_name)

        spec = CommandTagSpec(command=command, working_directory=working_directory)
        self.config.binaries[app_name][tag] = CommandTag(description=description, spec=spec)
        self.select(app_name, tag)

    def track_path(self, app_name: str, app_path: pathlib.Path, tag: Optional[str] = None,
                   description: Optional[str] = None, should_copy: bool = False, force: bool = False):
        if not app_path.exists():
            raise RichValueError("path {app_path} doesn't exist!", app_path=app_path)

        if tag is None:
            tag = str(uuid.uuid4())[:8]

        if app_name not in self.config.binaries:
            self.config.binaries[app_name] = BinaryStruct(name=app_name)

        app = self.config.binaries[app_name]
        # make sure we don't override selected tag if there's a drift
        if not force and tag in app.tags and app.selected is not None:
            self._unselect_current_tag(app)

        if should_copy:
            version_directory = self.settings.versions_path / app_name
            os.makedirs(version_directory, exist_ok=True)
            original_app_path = app_path
            app_path = version_directory / f'{app_name}_{tag}'
            if app_path.exists() and not force:
                raise RichValueError(f"Can not copy file to path - '{app_path}': already exists. "
                                     f"Please delete it manually or use -f flag")

            shutil.copy(original_app_path, app_path)
            os.chmod(app_path, 0o755)  # make sure it's executable

        self._dedup_paths(app_name, app_path, force=force)

        self.config.binaries[app_name][tag] = LinkTag(description=description,
                                                      spec=LinkTagSpec(path=app_path, is_copy=should_copy))
        self.select(app_name, tag, force=force)  # select added tag automatically

    def _dedup_paths(self, app_name: str, app_path: pathlib.Path, force: bool):
        copy_tags = {**self.config.binaries[app_name].tags}
        for existing_tag, binary_config in copy_tags.items():
            if isinstance(binary_config, LinkTag):
                if binary_config.spec.path == app_path:
                    if not force:
                        raise RichValueError("path '{app_path}' already exist at tag {tag} in {app_name} application! "
                                             "Use -f to force override",
                                             app_path=app_path, tag=existing_tag, app_name=app_name)

                    self.remove(app_name, existing_tag)

    def rename_tag(self, app_name: str, tag: str, new_tag: str):
        if app_name not in self.config.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.config.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        obj = self.config.binaries[app_name][tag]
        self.config.binaries[app_name][new_tag] = obj
        self.remove(app_name, tag, new_selected=new_tag)  # remove old tag

    def describe_tag(self, app_name: str, tag: str, description: str):
        if app_name not in self.config.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.config.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        obj = self.config.binaries[app_name][tag]
        obj.description = description

    def select(self, app_name: str, tag: Optional[str], force: bool = False):
        if app_name not in self.config.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag is not None and tag not in self.config.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        app = self.config.binaries[app_name]
        if not force and app.selected is not None:
            self._unselect_current_tag(app)

        if tag is not None:
            self._select_tag(app, tag)

    def _select_tag(self, app: BinaryStruct, tag: str):
        destination = self._get_destination_for(app)
        tag_struct = app.tags[tag]

        if isinstance(tag_struct, LinkTag):
            source = tag_struct.spec.path
            destination.symlink_to(source)

        if isinstance(tag_struct, CommandTag):
            with open(destination, 'w') as f:
                f.writelines([
                    "#!/bin/sh\n",
                    f"{PACKAGE_NAME} run {app.name} -- \"$@\"\n"
                ])

            os.chmod(destination, 0o755)

        app.selected = tag

    def _unselect_current_tag(self, app: BinaryStruct):
        self._assert_selected_owned_reference(app)
        destination = self._get_destination_for(app)
        # if the destination is a symlink, we can just unlink it
        # if it's a file, we need to remove it
        if destination.exists():
            if destination.is_symlink():
                destination.unlink()

            else:
                os.remove(destination)

        app.selected = None

    def _assert_selected_owned_reference(self, app: BinaryStruct):
        selected_tag = app.selected
        if selected_tag is None:
            return

        selected_struct = app.tags[selected_tag]
        if isinstance(selected_struct, LinkTag):
            destination = self._get_destination_for(app)
            if destination.is_symlink():
                actual_link = destination.readlink()
                if selected_struct.spec.path != actual_link:
                    raise RichValueError("DRIFT DETECTED! {app_path} is linked to a different binary, "
                                         "please remove existing link to continue using this link",
                                         app_path=str(destination))

            else:
                raise RichValueError("path {app_path} isn't a symlink and probably not managed by {package_name}",
                                     app_path=str(destination), package_name=PACKAGE_NAME)

    def _get_destination_for(self, app: BinaryStruct):
        if not self.settings.bin_resolved_path.exists():
            os.makedirs(self.settings.bin_resolved_path, exist_ok=True)

        return self.settings.bin_resolved_path / app.name

    def run(self, app_name: str, args: List[str]):
        if app_name not in self.config.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        app = self.config.binaries[app_name]
        if not app.selected:
            raise RichValueError("app {app_name} doesn't have any selected tag!", app_name=app.name)

        tag_struct = app.tags[app.selected]
        if not isinstance(tag_struct, CommandTag):
            raise RichValueError("tag {tag} of app {app_name} must be of type {tag_type} to be runnable",
                                 tag=app.selected, app_name=app.name, tag_type=tag_struct.kind)

        working_directory = None
        if tag_struct.spec.working_directory:
            if not tag_struct.spec.working_directory.exists():
                raise RichValueError("path '{path}' doesn't exists for command in tag {tag} of app {app_name}",
                                     path=tag_struct.spec.working_directory, tag=app.selected, app_name=app.name)

            working_directory = tag_struct.spec.working_directory

        user_command = shlex.split(tag_struct.spec.command)
        full_command = [*user_command, *args]

        process_env = {**os.environ}
        if tag_struct.spec.env is not None:
            for key, value in tag_struct.spec.env.items():
                process_env[key] = value

        subprocess.call(full_command, cwd=working_directory, env=process_env)

    def remove(self, app_name: str, tag: str, new_selected: Optional[str] = None):
        if app_name not in self.config.binaries:
            raise RichValueError("app {app_name} isn't tracked!", app_name=app_name)

        if tag not in self.config.binaries[app_name].tags:
            raise RichValueError("tag {tag} doesn't exist in application {app_name}", app_name=app_name, tag=tag)

        selected_tag = self.config.binaries[app_name].selected
        if selected_tag == tag:
            self.select(app_name, tag=new_selected)  # clear selected tag

        del self.config.binaries[app_name][tag]
