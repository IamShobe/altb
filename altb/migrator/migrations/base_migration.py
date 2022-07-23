import abc
import pathlib
from abc import ABC


MIGRATIONS_DIRECTORY = pathlib.Path(__file__).absolute().parent
SCHEMAS_DIRECTORY = MIGRATIONS_DIRECTORY / 'schemas'


class BaseMigration(ABC):
    EXPECTED_SCHEMA: pathlib.Path

    @abc.abstractmethod
    def migrate(self, input_config: dict) -> dict:
        return input_config

    @abc.abstractmethod
    def rollback(self, input_config: dict) -> dict:
        return input_config
