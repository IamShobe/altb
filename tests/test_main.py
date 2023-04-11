import os
import textwrap
import uuid
import tempfile
from pathlib import PosixPath

import pytest
import yaml
from typer.testing import CliRunner

from altb.main import app
from altb.model.config import AppConfig
from altb.model.tags import TagKind, LinkTagSpec, CommandTagSpec


@pytest.fixture()
def config_file_path():
    random_hash = uuid.uuid4()
    return f"/tmp/altb-{random_hash}.yaml"


@pytest.fixture()
def home_path():
    temp_dir = tempfile.TemporaryDirectory()
    yield temp_dir.name
    temp_dir.cleanup()


@pytest.fixture()
def runner(home_path: str):
    return CliRunner(
        env={
            "ALTB_HOME_PATH": home_path,
        }
    )


@pytest.fixture()
def random_file_path():
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write("some content\n".encode())
    temp_file.seek(0)
    yield temp_file.name
    temp_file.close()
    os.remove(temp_file.name)


def test_track_link(runner: CliRunner, random_file_path: str, home_path: str):
    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path],
    )

    assert result.exit_code == 0

    with open(f"{home_path}/.config/altb/config.yaml", "r") as f:
        content = AppConfig(**yaml.safe_load(f))

    assert "some-app" in content.binaries
    assert content.binaries["some-app"].selected == "latest"

    assert "latest" in content.binaries["some-app"].tags
    struct = content.binaries["some-app"].tags["latest"]
    assert struct.description is None
    assert struct.kind == TagKind.link
    assert isinstance(struct.spec, LinkTagSpec)
    assert struct.spec.path == PosixPath(random_file_path)
    assert struct.spec.is_copy is False


def test_copy_link(runner: CliRunner, random_file_path: str, home_path: str):
    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy"],
    )

    assert result.exit_code == 0

    with open(f"{home_path}/.config/altb/config.yaml", "r") as f:
        content = AppConfig(**yaml.safe_load(f))

    assert "some-app" in content.binaries
    assert content.binaries["some-app"].selected == "latest"

    assert "latest" in content.binaries["some-app"].tags
    struct = content.binaries["some-app"].tags["latest"]
    assert struct.kind == TagKind.link
    assert isinstance(struct.spec, LinkTagSpec)
    assert struct.spec.path != PosixPath(random_file_path)
    assert struct.spec.is_copy is True

    with open(struct.spec.path, "r") as f:
        copy_file_content = f.read()

    with open(random_file_path, "r") as f:
        original_file_content = f.read()

    assert copy_file_content == original_file_content


def test_copy_fail_if_destination_exists(runner: CliRunner, random_file_path: str, home_path: str):
    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy"],
    )

    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy"],
    )

    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_copy_success_if_force_when_destination_exists(runner: CliRunner, random_file_path: str, home_path: str):
    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy"],
    )

    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy", "--force"],
    )

    assert result.exit_code == 0

    with open(f"{home_path}/.config/altb/config.yaml", "r") as f:
        content = AppConfig(**yaml.safe_load(f))

    assert "some-app" in content.binaries
    assert content.binaries["some-app"].selected == "latest"


def test_copy_succeeds_if_was_link_before(runner: CliRunner, random_file_path: str, home_path: str):
    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path],
    )

    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["track", "path", "some-app@latest", random_file_path, "--copy"],
    )

    assert result.exit_code == 0


# command tests
def test_track_command(runner: CliRunner, home_path: str):
    result = runner.invoke(
        app,
        ["track", "command", "some-app@latest", "echo hello"],
    )

    assert result.exit_code == 0

    with open(f"{home_path}/.config/altb/config.yaml", "r") as f:
        content = AppConfig(**yaml.safe_load(f))

    assert "some-app" in content.binaries
    assert content.binaries["some-app"].selected == "latest"

    assert "latest" in content.binaries["some-app"].tags

    struct = content.binaries["some-app"].tags["latest"]
    assert struct.description is None
    assert struct.kind == TagKind.command
    assert isinstance(struct.spec, CommandTagSpec)
    assert struct.spec.command == "echo hello"
    assert struct.spec.working_directory is None
    assert struct.spec.env is None

    with open(f"{home_path}/.local/bin/some-app", "r") as f:
        file_content = f.read()

    assert file_content == textwrap.dedent("""\
    #!/bin/sh
    altb run some-app -- "$@"
    """)


def test_track_command_with_description(runner: CliRunner, home_path: str):
    # get new uuid for each test
    result = runner.invoke(
        app,
        ["track", "command", "some-app@latest", "echo hello", "-d", "some description"],
    )

    assert result.exit_code == 0

    with open(f"{home_path}/.config/altb/config.yaml", "r") as f:
        content = AppConfig(**yaml.safe_load(f))

    assert "some-app" in content.binaries
    assert content.binaries["some-app"].selected == "latest"

    assert "latest" in content.binaries["some-app"].tags
    struct = content.binaries["some-app"].tags["latest"]
    assert struct.description == "some description"
    assert struct.kind == TagKind.command
    assert isinstance(struct.spec, CommandTagSpec)
    assert struct.spec.command == "echo hello"
    assert struct.spec.working_directory is None
    assert struct.spec.env is None

    with open(f"{home_path}/.local/bin/some-app", "r") as f:
        file_content = f.read()

    assert file_content == textwrap.dedent("""\
    #!/bin/sh
    altb run some-app -- "$@"
    """)
