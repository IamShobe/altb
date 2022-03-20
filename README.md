# altb
altb is a cli utility influenced by `update-alternatives` of ubuntu.  
Linked paths are added to `$HOME/.local/bin` according to [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html).  
Config file is located at `$HOME/.config/altb/config.yaml`.

### How to start?
execute:
```bash
pipx install altb
```

to track new binary use:
```bash
altb track path <app_name>@<app_tag> /path/to/binary
```
for example:
```bash
altb track path python@2.7 /bin/python2.7
altb track path python@3.8 /bin/python3.8
# altb track python ~/Downloads/python # will also work and generate a new hash for it
```

List all tracked versions:
```bash
$ altb list -a
python
|----   2.7 - /bin/python2.7
|----   3.8 - /bin/python3.8
```

Use specific version:
```bash
altb use <app_name>[@<app_tag>]
```

example:
```bash
altb use python@2.7
```
this will link the tracked path to `~/.local/bin/<app_name>` in this case - `~/.local/bin/python`

Copy specific standalone binary automatically to `~/.local/altb/versions/<app_name>/<app_name>_<tag>`
```bash
altb track path helm@3 ~/Downloads/helm --copy
```

You can run custom commands using:
```bash
altb track command special_command@latest "echo This is a command"
```
this especially useful for latest developments, example:
```bash
altb track command special_command@latest "go run ./cmd/special_command" --working-directory "$HOME/special_command"
```
