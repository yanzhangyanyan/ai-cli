# Contributing to aiCLI

Thank you for your interest in contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/chzy40307891/aicli.git
cd aicli
uv sync
```

## Making Changes

1. Create a branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Test: `uv run aicli --local` and try a few tasks
4. Submit a Pull Request

## Code Style

- Python 3.11+
- Keep it simple — no unnecessary abstractions
- All user-facing strings go through `i18n.t()` for bilingual support

## Reporting Issues

- Describe what you expected to happen
- Include the command you ran
- Include the error output (redact any API keys or passwords)
- Include your OS and Python version

## Feature Requests

We welcome ideas! Please open an issue with:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered
