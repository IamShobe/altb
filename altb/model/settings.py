import pathlib
from typing import Optional

from pydantic import BaseSettings

from altb.common.constants import PACKAGE_NAME


class Settings(BaseSettings):
    home_path: pathlib.Path = pathlib.Path.home()
    config_path: Optional[pathlib.Path] = None
    bin_path: Optional[pathlib.Path] = None
    data_path: Optional[pathlib.Path] = None

    @property
    def config_resolved_path(self) -> pathlib.Path:
        return self.config_path or (self.home_path / '.config' / f'{PACKAGE_NAME}' / 'config.yaml').resolve()

    @property
    def bin_resolved_path(self) -> pathlib.Path:
        return self.bin_path or (self.home_path / '.local' / 'bin').resolve()

    @property
    def data_resolved_path(self) -> pathlib.Path:
        return self.data_path or (self.home_path / '.local' / 'share' / f'{PACKAGE_NAME}').resolve()

    @property
    def versions_path(self) -> pathlib.Path:
        return self.data_resolved_path / 'versions'

    class Config(BaseSettings.Config):
        env_prefix = f'{PACKAGE_NAME}_'
