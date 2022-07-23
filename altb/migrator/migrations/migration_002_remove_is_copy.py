from .base_migration import BaseMigration, SCHEMAS_DIRECTORY


class MigrationRemoveIsCopy(BaseMigration):
    EXPECTED_SCHEMA = SCHEMAS_DIRECTORY / "002_AppConfig.json"

    def migrate(self, input_config: dict) -> dict:
        for binary in input_config['binaries'].values():
            for tag in binary['tags'].values():
                if tag['kind'] == 'link':
                    del tag['spec']['is_copy']

        return input_config

    def rollback(self, input_config: dict) -> dict:
        return input_config
