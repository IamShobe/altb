from enum import Enum


class ConfigVersion(str, Enum):
    v0_0_0 = "0.0.0"
    v0_1_0 = "0.1.0"
    latest = v0_1_0
