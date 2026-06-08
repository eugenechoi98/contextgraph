# ContextGraph Studio Release Checklist

## Repository

- [ ] git status clean
- [ ] LICENSE present
- [ ] README reviewed
- [ ] no secrets
- [ ] no tracked databases, caches, reports, or virtualenvs

## Validation

- [ ] pytest tests passes
- [ ] wheel builds
- [ ] sdist builds
- [ ] wheel clean install smoke passes
- [ ] MCP stdio wheel smoke passes
- [ ] uvx local wheel smoke passes

## GitHub

- [x] public repository created
- [x] repository URL added to pyproject.toml
- [ ] CI passes on GitHub Actions
- [ ] initial tag reviewed

## Publication

- [ ] decide whether to publish PyPI
- [ ] do not publish without Eugene confirmation
