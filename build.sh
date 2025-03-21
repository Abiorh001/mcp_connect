#!/bin/bash

# Clean up any previous builds
rm -rf dist/ build/ *.egg-info/

# Build the package
hatch build

# Check the distribution
twine check dist/*

echo "Build complete! To publish to PyPI, run:"
echo "twine upload dist/*" 