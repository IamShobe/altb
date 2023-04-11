import abc
import pathlib
from enum import Enum
from typing import Optional, Literal, Annotated, Union, Dict

import pydantic
from pydantic import BaseModel, BaseConfig, StrictBool, StrictStr, Field


class TagKind(str, Enum):
    link = "link"
    command = "command"


class BaseTag(BaseModel, abc.ABC):
    kind: TagKind
    description: Optional[str]
    spec: BaseModel

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash((self.kind, hash(self.spec)))

    def __eq__(self, other):
        return hash(self) == hash(other)


class LinkTagSpec(BaseModel):
    path: pathlib.Path
    is_copy: Optional[StrictBool] = False

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        return hash(self) == hash(other)


class LinkTag(BaseTag):
    kind: Literal[TagKind.link] = TagKind.link
    spec: LinkTagSpec


class CommandTagSpec(BaseModel):
    command: str
    working_directory: Optional[pathlib.Path]
    env: Optional[dict[StrictStr, StrictStr]] = None

    class Config(BaseConfig):
        extra = pydantic.Extra.forbid

    def __hash__(self):
        return hash(self.command)

    def __eq__(self, other):
        return hash(self) == hash(other)


class CommandTag(BaseTag):
    kind: Literal[TagKind.command] = TagKind.command
    spec: CommandTagSpec


TagConfig = Annotated[Union[CommandTag, LinkTag], Field(discriminator="kind")]

TagDict = Dict[str, TagConfig]
