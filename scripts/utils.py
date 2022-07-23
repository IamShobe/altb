import os
import pathlib
import re
from dataclasses import dataclass

import typer
from pydash.strings import snake_case
from jinja2 import Environment, FileSystemLoader

from altb.config import AppConfig
from altb.migrator.migrations.base_migration import SCHEMAS_DIRECTORY, MIGRATIONS_DIRECTORY

SCHEMA_FILENAME_PATTERN = re.compile(r"(?P<name>(?P<count>\d{3})_.*)\.json")
MIGRATION_FILENAME_PATTERN = re.compile(r"(?P<name>migration_(?P<count>\d{3})_.*)\.py")

DIRECTORY = pathlib.Path(__file__).absolute().parent


env = Environment(
    loader=FileSystemLoader(DIRECTORY / 'templates'),
    extensions=['jinja2_strcase.StrcaseExtension'],
)


app = typer.Typer()


@dataclass
class Schema:
    name: str
    path: str


def get_latest_id(path: pathlib.Path, pattern: re.Pattern):
    if not path.exists():
        return 0

    latest = 0
    for filename in os.listdir(path):
        match = pattern.match(filename)
        if match is None:
            continue

        count = int(match.group('count'))
        if count > latest:
            latest = count

    return latest


def generate_new_schema(schema_directory: pathlib.Path):
    os.makedirs(schema_directory, exist_ok=True)

    schema_id = get_latest_id(schema_directory, pattern=SCHEMA_FILENAME_PATTERN) + 1
    schema_name = f"{schema_id:03d}_AppConfig.json"

    with open(schema_directory / schema_name, "w") as f:
        f.write(AppConfig.schema_json())

    return schema_name


@app.command()
def generate_migrations(migration_name: str):
    os.makedirs(MIGRATIONS_DIRECTORY, exist_ok=True)
    schema_name = generate_new_schema(SCHEMAS_DIRECTORY)

    migration_id = get_latest_id(MIGRATIONS_DIRECTORY, pattern=MIGRATION_FILENAME_PATTERN) + 1
    file_name = f"migration_{migration_id:03d}_{snake_case(migration_name)}.py"

    template = env.get_template('migrations.py.jinja2')

    with open(MIGRATIONS_DIRECTORY / file_name, "w") as f:
        f.write(template.render(migration_name=migration_name, schema_file=schema_name))


@app.command()
def test():
    pass


def main():
    app()


if __name__ == '__main__':
    main()
