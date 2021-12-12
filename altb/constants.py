import pathlib
from typing import TypedDict

PACKAGE_NAME = "altb"

CONFIG_FILE = (pathlib.Path.home() / f'.{PACKAGE_NAME}' / 'config.yaml').resolve()


class TypeColor(TypedDict):
    tag: str
    app_name: str
    app_path: str


TYPE_TO_COLOR: TypeColor = {
    "tag": "bold slate_blue3",
    "app_name": "bold orange3",
    "app_path": "bold green4",
}
