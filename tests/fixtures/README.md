# Test Fixtures

This directory contains reusable test data and fixtures for the Huntable CTI Studio test suite.

## Directory Structure

- `rss/` - RSS and Atom feed samples
- `html/` - HTML page samples (valid and malformed)
- `sigma/` - SIGMA YAML rule samples (valid, invalid, round-trip)
- `similarity/` - Similarity search inputs and expected outputs (golden files)
- `articles/` - Article JSON samples

## Usage

Fixtures should be used instead of inline test data to:
- Ensure consistency across tests
- Enable deterministic testing
- Reduce test maintenance burden
- Support golden file comparisons

## Golden Files

Golden files (especially in `similarity/`) include version metadata and invariants.
See `similarity/README.md` for details on versioning and update process.
