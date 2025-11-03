# Contributing to Azazel-Pi

We welcome contributions to the Azazel-Pi project! This document provides guidelines for developers who want to contribute code, documentation, or bug reports.

## Development Environment Setup

### Prerequisites

- Raspberry Pi OS (64-bit) or compatible Debian-based system
- Python 3.8+
- Git

### Initial Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/01rabbit/Azazel-Pi.git
   cd Azazel-Pi
   ```

2. **Install development dependencies**:
   ```bash
   # Install test dependencies
   pip3 install pytest pytest-cov pyyaml requests rich
   
   # Or install with optional test dependencies
   pip3 install -e ".[test]"
   ```

3. **Verify installation**:
   ```bash
   python3 -c "import azazel_pi; print('Import successful')"
   ```

## Running Tests

### Test Suite Structure

The test suite is organized under `tests/` with the following structure:
- `tests/conftest.py` - Test configuration and fixtures
- `tests/core/` - Core functionality tests
- `tests/monitor/` - Monitoring component tests  
- `tests/utils/` - Utility function tests

### Running Tests

```bash
# Run all tests
python3 -m pytest

# Run tests with coverage report
python3 -m pytest --cov=azazel_pi

# Run specific test modules
python3 -m pytest tests/core/test_state_machine.py

# Run tests with verbose output
python3 -m pytest -v

# Run tests matching a pattern
python3 -m pytest -k "test_config"
```

### Using Makefile

The project includes a Makefile for common development tasks:

```bash
# Run linting checks
make lint

# Run test suite  
make test

# Create distribution package
make package
```

### Test Configuration

Tests are configured via `pytest.ini` and `pyproject.toml`:
- Test discovery: `test_*.py` files
- Coverage target: `azazel_pi` module
- Markers: `unit`, `integration`, `slow`

### Writing Tests

#### Test Fixtures

Common fixtures are available in `conftest.py`:
- `temp_config_dir` - Temporary directory for test configs
- `mock_notify_yaml` - Mock notification configuration
- `mock_azazel_yaml` - Mock main configuration

#### Example Test Structure

```python
def test_example_function(mock_azazel_yaml):
    """Test description following pytest conventions."""
    # Arrange
    config = AzazelConfig.from_file(mock_azazel_yaml)
    
    # Act
    result = example_function(config)
    
    # Assert
    assert result.status == "expected_value"
```

#### Test Categories

Use pytest markers to categorize tests:
```python
import pytest

@pytest.mark.unit
def test_unit_function():
    """Fast, isolated unit test."""
    pass

@pytest.mark.integration  
def test_integration_scenario():
    """Integration test with external dependencies."""
    pass

@pytest.mark.slow
def test_slow_operation():
    """Test that takes significant time to run."""
    pass
```

## Code Quality

### Linting

The project uses several linting tools:
- **shellcheck** for shell scripts
- **JSON validation** for configuration schemas
- **File existence checks** for critical scripts

Run linting before submitting:
```bash
make lint
```

### Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Write docstrings for public functions
- Keep functions focused and testable

## Development Workflow

### Making Changes

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with appropriate tests

3. **Run the test suite**:
   ```bash
   make test
   make lint
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: add feature description"
   ```

5. **Push and create pull request**:
   ```bash
   git push origin feature/your-feature-name
   ```

### Pull Request Guidelines

- Include tests for new functionality
- Update documentation as needed
- Ensure all tests pass
- Follow conventional commit message format
- Provide clear description of changes

## Testing Components

### State Machine Tests (`test_state_machine.py`)

Tests the core defensive mode transitions (Portal → Shield → Lockdown).

Key test areas:
- State transition logic
- Event processing
- Configuration loading
- Time-based unlocking

### Configuration Tests (`test_config.py`)

Tests configuration file loading and validation.

Key test areas:
- YAML file parsing
- Required field validation
- Default value handling
- Schema compliance

### Ingestion Tests (`test_ingest.py`)

Tests log processing from Suricata and OpenCanary.

Key test areas:
- JSON log parsing
- Event generation
- File tailing behavior
- Error handling

### Action Tests (`test_actions.py`)

Tests traffic control and firewall actions.

Key test areas:
- Command generation
- Idempotent operations
- Parameter validation
- Action planning

## Debugging Tests

### Running Tests in Debug Mode

```bash
# Run with pdb on failures
python3 -m pytest --pdb

# Run with detailed output
python3 -m pytest -vvv --tb=long

# Run specific test with print statements
python3 -m pytest tests/core/test_config.py::test_config_from_file -s
```

### Test Data and Fixtures

Test fixtures create temporary directories and mock configurations:
- Use `temp_config_dir` for filesystem tests
- Mock external dependencies (Mattermost, Suricata)
- Keep test data minimal and focused

## Documentation

When contributing code, also update:
- Function docstrings
- README.md if adding user-facing features
- API_REFERENCE.md for new modules
- This CONTRIBUTING.md for process changes

## Getting Help

- Check existing issues and discussions
- Review test files for usage examples
- Read the architecture documentation in `docs/ARCHITECTURE.md`
- Contact maintainers for complex changes

## Security Considerations

- Never commit sensitive data or credentials
- Test security-related changes thoroughly
- Follow responsible disclosure for security issues
- Use GitHub's private vulnerability reporting

---

Thank you for contributing to Azazel-Pi! Your help makes this project better for everyone.