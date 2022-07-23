from .base_migration import BaseMigration, SCHEMAS_DIRECTORY


class MigrationInitial(BaseMigration):
    EXPECTED_SCHEMA = SCHEMAS_DIRECTORY / "001_AppConfig.json"

    def migrate(self, input_config: dict) -> dict:
        return input_config

    def rollback(self, input_config: dict) -> dict:
        return input_config
