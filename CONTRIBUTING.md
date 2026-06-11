# Contributing to SponsorScout

Thank you for considering contributing to SponsorScout! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/SponsorScout.git
   cd SponsorScout
   ```
3. **Create a virtual environment** and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   pip install -r requirements.txt
   pip install pytest
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/my-feature
   ```

## Making Changes

- **Write clean, modern Python 3.10+ code.** No Python 2 compatibility.
- Follow the existing code style — use the same indentation (4 spaces), naming conventions, and inline comment style.
- **Write tests** for any new features or bug fixes. Run the test suite before committing:
  ```bash
  pytest tests/ -q
  ```
- **Keep commits focused** — one logical change per commit, with clear commit messages.

## Commit Messages

Use clear, descriptive commit messages. Examples:
- `fix: correct URL parsing for Workday connector`
- `feat: add AI rating for job listings`
- `docs: update README with install instructions`
- `refactor: move ensure_table to database initialization`

## Opening a Pull Request

1. Push your changes to your fork
2. Open a pull request against `main`
3. Include a clear description of what changes you made and why
4. Ensure all tests pass

## Reporting Bugs

If you find a bug, please open an issue with:
- A clear title and description
- Steps to reproduce the issue
- Expected vs. actual behavior
- Your Python version and OS

## Questions or Discussions

For general questions about the project, open a discussion on GitHub.

## License

By contributing, you agree that your contributions will be licensed under the MIT License (the same as the project).