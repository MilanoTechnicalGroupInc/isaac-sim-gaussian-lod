## Summary

Describe what changed and why.

## Validation

- [ ] `python -m ruff check .`
- [ ] `python -m pytest`
- [ ] `python -m build` when packaging is affected
- [ ] Isaac Sim validation when runtime or extension behavior is affected

## Safety and compatibility

- [ ] No credentials, proprietary assets, machine-specific paths, or generated outputs are included
- [ ] User-controlled paths and external commands have been reviewed
- [ ] Documentation and changelog entries are updated when behavior changes
