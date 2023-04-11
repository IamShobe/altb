from typing import TypedDict

PACKAGE_NAME = "altb"


class TypeColor(TypedDict):
    tag: str
    app_name: str
    app_path: str
    tag_type: str
    command: str


TYPE_TO_COLOR: TypeColor = {
    "tag": "bold slate_blue3",
    "app_name": "bold orange3",
    "app_path": "bold green4",
    "tag_type": "bold deep_pink1",
    "command": "bold violet",
}
