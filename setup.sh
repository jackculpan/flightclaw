#!/bin/bash
set -e

echo "Installing flight-tracker dependencies..."
pip install flights
mkdir -p "$(dirname "$0")/data"
echo "Done. flight-tracker is ready to use."
