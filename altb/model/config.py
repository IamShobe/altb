import pathlib
from typing import Optional, Dict

import pydantic
from pydantic import BaseModel, BaseConfig

from .tags import TagDict


class BinaryStruct(BaseModel):
    name: str
    tags: TagDict = {}
    selected: Optional[str] = None

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __getitem__(self, item):
        return self.tags[item]

    def __setitem__(self, key, value):
        self.tags[key] = value

    def __delitem__(self, key):
        del self.tags[key]


class AppConfig(BaseModel):
    binaries: Dict[str, BinaryStruct] = {}

    class Config(BaseConfig):
        json_encoders = {
            pathlib.Path: str,
            set: list,
        }
        extra = pydantic.Extra.forbid

