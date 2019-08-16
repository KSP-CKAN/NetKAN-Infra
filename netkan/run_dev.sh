#!/bin/bash
pip install --user -e netkan/.
echo "Running with the following arguments: $@"
.local/bin/netkan "$@"
