# AI Agent Startup Instructions

## Purpose
This file describes general startup and best-practice rules for an AI agent working on a new software project.

Use it as a generic onboarding guide whenever a new repository is started or when a code base needs an AI agent to begin work safely.

---

## Guiding Principles
1. Security first.
2. Code quality before feature expansion.
3. Automated checks are mandatory.
4. Documentation must reflect changes.
5. Keep changes small, testable, and reversible.

---

## Initial AI Agent Workflow
1. Read this file first.
2. Inspect the repository structure and root files.
3. Identify the main application language and framework.
4. Locate configuration files, dependency manifests, and test suites.
5. Confirm that sensitive data is not committed.
6. Validate the development environment before making changes.

---

## Prerequisite Checks
Verify the following as applicable to the project:
- `README.md` exists and describes the project.
- Dependency manifest exists (`pyproject.toml`, `requirements.txt`, `package.json`, `Gemfile`, etc.).
- Code style and linting config exists (`.pre-commit-config.yaml`, `.editorconfig`, `ruff.toml`, etc.).
- Tests are present (`tests/`, `spec/`, or project-specific test directories).
- CI/CD definitions exist (`.github/workflows/`, `azure-pipelines.yml`, `Jenkinsfile`, etc.).
- Secret management guidance exists (`.env.example`, `SECRETS_MANAGEMENT.md`, or docs).

---

## Security Best Practices
Always make security the baseline:
- Do not add or commit secrets into source control.
- Use `.env.example` or config templates, never real keys.
- Prefer environment variables or secret management systems.
- Verify that any Docker/Kubernetes config follows least privilege.
- Use immutable dependency versions where possible.
- Run dependency security scans regularly.

Common security tools:
- `pre-commit` with security hooks
- `bandit`, `semgrep`, `safety`, `pip-audit`, `npm audit`
- `trivy`, `docker scan`
- static analyzers and vulnerability scanners

---

## Code Management Best Practices
For every code change:
- Create a feature branch with a clear name.
- Keep commits focused and atomic.
- Add or update tests for new behavior.
- Run formatting and linting locally before pushing.
- Review changes for security and correctness.
- Update documentation when functionality or behavior changes.

Common Git workflow:
- `git checkout -b feature/<short-description>`
- `git add .`
- `git commit -m "<summary of change>"`
- `git push origin <branch>`

---

## Pre-commit and Quality Gates
If the repository includes `.pre-commit-config.yaml`, use it.

Recommended setup:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .[dev]
pre-commit install
pre-commit run --all-files
```

If pre-commit is not present, identify the equivalent project tooling and run it.

Desired checks include:
- formatting (`black`, `prettier`, `clang-format`)
- linting (`ruff`, `eslint`, `flake8`, `pylint`)
- import sorting (`isort`)
- type checking (`mypy`, `pyright`)
- security scanning (`bandit`, `pip-audit`, `npm audit`)
- docs and markdown linting

---

## Testing
Always run the available test suite before and after changes.

Common commands:
```bash
pytest tests/ -v
npm test
bundle exec rspec
```

If coverage tooling is configured, use it:
```bash
pytest --cov
npm run coverage
```

If the project has no tests, prioritize adding at least one regression test for any new feature or bug fix.

---

## Dependency Management
Keep dependencies explicit and stable.
- Prefer pinned versions over floating ranges.
- Review new dependency additions for security and maintenance risk.
- Use dependency scanners when available.
- Avoid unnecessary packages.

If a dependency is added:
- add it to the project manifest
- ensure it is installed in the development environment
- run formatting, linting, and tests again

---

## Documentation
Keep documentation current.
- Update `README.md` for user-facing changes.
- Add or update docs for new architecture, tooling, or workflow changes.
- Document environment variables and secrets handling.
- Explain how to run the app and tests.

If docs are missing, create a minimal `README.md` with:
- project summary
- setup steps
- run commands
- test commands
- security notes

---

## Deployment and Infrastructure
If the project includes deployment or infrastructure files:
- inspect Dockerfiles, Kubernetes manifests, Helm charts, and compose files.
- ensure build artifacts and secrets are not committed.
- verify that deployment configs follow security best practices.
- lint or validate manifests where possible.

Common commands:
- `docker compose config`
- `helm lint` or `kubectl apply --dry-run=client`
- `terraform validate`

---

## AI Agent Behavior Rules
When modifying the project:
- prioritize safety and maintainability.
- keep changes small and well-tested.
- do not introduce hidden or undocumented behavior.
- do not commit or expose secrets.
- follow existing repo conventions.
- if unsure, ask for clarification or document assumptions.

---

## Recommended Starting Checklist
1. Read this file.
2. Inspect project structure and key files.
3. Confirm there is no exposed secret data.
4. Set up the local environment.
5. Run available formatting, linting, and pre-commit checks.
6. Run the test suite.
7. Run dependency and security scans if available.
8. Make the change with tests.
9. Update documentation.
10. Summarize the result clearly.

---

## Notes for AI Agents
This is a generic startup guide. Use it as the baseline for any new software project.
If project-specific tools or workflows exist, adapt the workflow accordingly but keep the core principles:
- security first
- automation second
- tests always
- docs updated

If the project lacks any of these capabilities, note that clearly and proceed with conservative, safe choices.
