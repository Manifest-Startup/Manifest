#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# The return value of a pipeline is the status of the last command to exit with a non-zero status,
# or zero if no command exited with a non-zero status.
set -o pipefail

# Create coverage directory if it doesn't exist
mkdir -p ../docs/backend-coverage/html

# Set PYTHONPATH to the backend directory so 'app' is importable
# Run pytest, show long test summary info, and be verbose.
# Pipe output to tee to save to a file and print to stdout.
PYTHONPATH=$(pwd) pytest --tb=long -v | tee ../docs/backend-coverage/test-report.txt

# The exit code of the pipeline is now the exit code of pytest.
# The rest of the script will only execute if pytest succeeds.

echo "✅ All tests passed!"
echo "📊 Coverage reports generated in:"
echo "   - docs/backend-coverage/html/index.html (HTML report)"
echo "   - docs/backend-coverage/coverage.xml (XML report)"
echo "📝 Detailed test log: docs/backend-coverage/test-report.txt" 