# CLAUDE.md

## Testing

After making any code changes, always run the tests:

```bash
source venv/bin/activate && python -m pytest -v
```

To skip slow network tests: `python -m pytest -m "not integration" -v`

## Bash completion

- The completion script is `bash_completion.d/ck` and is **symlinked** (not copied) by `install-osx.sh` into brew's completion dir. Edits take effect in new terminals.
- User runs **macOS default bash 3.2**. Do NOT use `compopt` or other bash 4+ builtins.
- Tags with subtags must show a trailing `/` in completion (e.g., `sigs/`) so the user can keep tabbing to browse deeper.
