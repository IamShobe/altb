import json
from copy import deepcopy
from typing import List, Type
from dataclasses import dataclass

from jsonschema import validate

from .versions import ConfigVersion
from .migrations.base_migration import BaseMigration
from .migrations.migration_001_initial import MigrationInitial
from .migrations.migration_002_remove_is_copy import MigrationRemoveIsCopy


@dataclass
class MigrationConfig:
    version: ConfigVersion
    migration_class: Type[BaseMigration]


migrations: List[MigrationConfig] = [
    MigrationConfig(ConfigVersion.v0_0_0, MigrationInitial),
    MigrationConfig(ConfigVersion.v0_1_0, MigrationRemoveIsCopy),
]


def is_migrated(current_version: ConfigVersion) -> bool:
    return migrations[-1].version == current_version


def migration_index(version: ConfigVersion):
    for i, config in enumerate(migrations):
        if config.version == version:
            return i

    return -1


def migrate(config: dict) -> dict:
    version: ConfigVersion
    if 'version' not in config:
        version = ConfigVersion.v0_0_0
    else:
        version = ConfigVersion(config['version'])

    index = migration_index(version)

    print(f"detected config version of - {version}")
    current_config = deepcopy(config)
    migrations_needed = migrations[index+1:]
    print(f"{len(migrations_needed)} migrations needed")
    for migration in migrations_needed:
        print(f"\tmigrating config to - {migration.version}")
        instance = migration.migration_class()
        current_config = instance.migrate(current_config)
        current_config['version'] = str(migration.version.value)

        with open(instance.EXPECTED_SCHEMA) as f:
            schema = json.load(f)

        validate(instance=current_config, schema=schema)

    print("done!")
    return current_config
