# Contributing to Climate Monitor

Thank you for your interest in contributing to the Climate Monitor project! We welcome contributions from the community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)
- [Translation Contributions](#translation-contributions)

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/ClimateMonitor.git
   cd ClimateMonitor
   ```
3. **Add the upstream repository**:
   ```bash
   git remote add upstream https://github.com/CervezaStallone/ClimateMonitor.git
   ```

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Clear title and description**
- **Steps to reproduce** the behavior
- **Expected behavior** vs actual behavior
- **Screenshots** if applicable
- **Environment details** (OS, Python version, etc.)
- **Log output** from terminal/console

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, include:

- **Clear title and description**
- **Use case** - explain why this enhancement would be useful
- **Possible implementation** if you have ideas
- **Screenshots or mockups** if applicable

### Code Contributions

1. **Check existing issues** or create a new one to discuss your idea
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following our coding standards
4. **Test your changes** thoroughly
5. **Commit your changes** using conventional commits
6. **Push to your fork** and submit a pull request

## Development Setup

### Prerequisites

- Python 3.9 or higher
- Virtual environment tool (venv)
- Git
- XY-MD02 sensor (for hardware testing) or mock data

### Setup Instructions

1. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1  # Windows PowerShell
   # or
   source .venv/bin/activate  # Linux/macOS
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

5. **Run tests** (if available):
   ```bash
   python test_app.py
   ```

## Coding Standards

### Python Style Guide

- Follow **PEP 8** style guidelines
- Use **4 spaces** for indentation (no tabs)
- Maximum line length: **120 characters**
- Use **meaningful variable names**
- Add **docstrings** to functions and classes

### Code Organization

The project follows a modular architecture:

```
ClimateMonitor/
├── app.py                    # Entry point
├── database.py               # Database operations
├── modbus_reader.py          # Modbus communication
├── psychrometric.py          # Psychrometric calculations
├── callbacks.py              # Dash callbacks
├── layout.py                 # UI components
└── translations.py           # Multi-language support
```

**When adding new features:**
- Place database-related code in `database.py`
- Place Modbus logic in `modbus_reader.py`
- Place UI callbacks in `callbacks.py`
- Place layout components in `layout.py`
- Update translations for all supported languages

### Documentation

- Add comments for complex logic
- Update README.md if adding new features
- Include docstrings with parameter descriptions
- Update `.env.example` if adding new configuration options

## Commit Guidelines

We follow **Conventional Commits** specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependencies

### Examples

```bash
feat(translations): Add Italian language support

- Add Italian translations for all 65 keys
- Update language selector dropdown
- Test all UI elements with Italian

Closes #123
```

```bash
fix(database): Correct timezone conversion in queries

The previous implementation interpreted local timestamps as UTC,
causing a 1-hour offset in displayed times.

Fixes #456
```

## Pull Request Process

1. **Update documentation** if needed (README.md, docstrings)
2. **Ensure all tests pass** (run `python test_app.py`)
3. **Update translations** if you modified UI text
4. **Keep commits clean** - consider squashing related commits
5. **Write a clear PR description**:
   - What does this PR do?
   - Why is this change needed?
   - How has it been tested?
   - Screenshots (if UI changes)

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
- [ ] Tests pass
- [ ] All translations updated (if applicable)
- [ ] Commit messages follow conventions

## Testing

### Manual Testing

Before submitting a PR, test:

1. **Application startup** - no errors in console
2. **Basic functionality** - all features work as expected
3. **Language switching** - test all supported languages (NL, EN, DE, FR, ES)
4. **Data visualization** - graphs render correctly
5. **Responsive design** - test on different screen sizes
6. **Error handling** - test edge cases

### Automated Testing

If `test_app.py` exists, run it:

```bash
python test_app.py
```

All tests must pass before merging.

## Translation Contributions

We support 5 languages: **Dutch (NL), English (EN), German (DE), French (FR), Spanish (ES)**

### Adding/Updating Translations

1. Open `translations.py`
2. Find the translation key you want to add/update
3. Add/update the translation for **all 5 languages**
4. Ensure consistency in tone and terminology
5. Test the UI with your translations

### Translation Guidelines

- Keep translations **concise** for UI labels
- Maintain **technical accuracy** for sensor terms
- Use **formal tone** (not overly casual)
- Test for **text overflow** in UI elements
- Match emoji usage where culturally appropriate

### Adding a New Language

To add a new language:

1. Add language code to `LANGUAGE_NAMES` in `translations.py`
2. Add complete translation dictionary with all 65+ keys
3. Test thoroughly in the UI
4. Update README.md to mention the new language
5. Submit PR with screenshots showing the new language

## Questions?

If you have questions about contributing:

- Check existing **GitHub Issues** and **Pull Requests**
- Read the **README.md** for project overview
- Review the **Code of Conduct**
- Open a new issue with the `question` label

---

**Thank you for contributing to Climate Monitor!** 🎉
