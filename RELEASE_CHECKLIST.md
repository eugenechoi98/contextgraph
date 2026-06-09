# ContextGraph Studio Release Checklist

## Repository

- [x] git status clean
- [x] LICENSE present
- [x] README reviewed
- [x] no secrets
- [x] no tracked databases, caches, reports, or virtualenvs

## Validation

- [x] pytest tests passes
- [x] wheel builds
- [x] sdist builds
- [x] wheel clean install smoke passes
- [ ] MCP stdio wheel smoke passes
- [x] uvx local wheel smoke passes
- [x] pip install smoke passes from PyPI
- [x] uvx smoke passes from PyPI

## GitHub

- [x] public repository created
- [x] repository URL added to pyproject.toml
- [x] CI passes on GitHub Actions
- [x] v0.1.0 tag created
- [x] GitHub Release published

## Publication

- [x] PyPI contextgraph-studio 0.1.0 published
- [x] do not publish without Eugene confirmation

## Boundaries

- [ ] full SWE-bench Lite benchmark executed
- [ ] Docker harness executed
- [ ] patch apply executed
- [ ] target repo tests executed
