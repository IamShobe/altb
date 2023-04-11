# Migrate to v0.5.0 and above from lower versions

In version 0.5.0 altb uses `~/.local/share/altb` as data directory instead of `~/.local/altb`.  
To migrate your data to the new directory run:
```shell
bash ./scripts/migrations/2023_04_11_migrate_0_5_0.sh
```