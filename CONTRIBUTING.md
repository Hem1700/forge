# Contributing to FORGE

Thanks for your interest in contributing. FORGE is an MIT-licensed project and welcomes bug reports, feature requests, and pull requests.

---

## Getting Started

1. Fork the repo and create your branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. Set up the dev environment — see the [README](README.md#getting-started) for full instructions.
3. Make your changes, write tests where applicable, and confirm everything passes.
4. Open a pull request against `main`.

---

## What to Work On

Check the [Issues](https://github.com/Hem1700/forge/issues) tab for open bugs and feature requests. Issues labelled `good first issue` are good starting points.

If you want to add something not tracked yet, open an issue first so we can discuss the approach before you invest time building it.

---

## Pull Request Guidelines

- **One concern per PR** — bug fixes and features should be separate PRs.
- **Tests required** — any backend change should include or update tests in `backend/tests/`. Run `pytest` before submitting.
- **TypeScript must compile** — frontend changes must pass `npx tsc --noEmit`.
- **Keep scope tight** — don't refactor surrounding code that wasn't part of the task. Focused PRs are easier to review and merge faster.
- **Describe what and why** — the PR description should explain what changed and why, not just repeat the commit messages.

---

## Code Style

### Backend (Python)
- Follow existing patterns in the file you're modifying.
- Use `async/await` throughout — FORGE is fully async.
- Type annotations on all new functions.
- No external dependencies added without discussion.

### Frontend (TypeScript + React)
- Functional components with hooks only.
- Tailwind for styling — no new CSS files.
- Follow the naming and file structure in `frontend/src/`.

### CLI (Python + Click + Rich)
- New commands go in `cli/forge_cli/main.py`.
- Display helpers (tables, panels, syntax) go in `cli/forge_cli/display.py`.
- Match the output style of existing commands.

---

## Reporting Bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) when opening an issue. Include reproduction steps, expected vs. actual behavior, and relevant logs.

For **security vulnerabilities**, do not open a public issue — see [SECURITY.md](SECURITY.md).

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers this project. Your copyright is retained — the MIT License does not transfer ownership, it grants permission.
