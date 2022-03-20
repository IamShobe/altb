import pathlib
from typing import TypedDict

PACKAGE_NAME = "altb"

CONFIG_FILE = (pathlib.Path.home() / '.config' / f'{PACKAGE_NAME}' / 'config.yaml').resolve()

LOCAL_DIRECTORY = (pathlib.Path.home() / '.local' / f'{PACKAGE_NAME}').resolve()
VERSIONS_DIRECTORY = (LOCAL_DIRECTORY / 'versions').resolve()


class TypeColor(TypedDict):
    tag: str
    app_name: str
    app_path: str


TYPE_TO_COLOR: TypeColor = {
    "tag": "bold slate_blue3",
    "app_name": "bold orange3",
    "app_path": "bold green4",
    "tag_type": "bold deep_pink1",
    "command": "bold violet",
}
