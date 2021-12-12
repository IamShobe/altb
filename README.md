# altb
altb is a cli utility influenced by `update-alternatives` of ubuntu.  
Linked paths are added to `$HOME/.local/bin` according to [XDG Base Directory Specification](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html)

### How to start?
execute:
```bash
pipx install altb
```

to track new binary use:
```bash
altb track <app_name>@<app_tag> /path/to/binary
```
for example:
```bash
altb track python@2.7 /bin/python2.7
altb track python@3.8 /bin/python3.8
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
