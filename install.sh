#!/bin/sh
set -eu
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_command=''
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        python_command=$candidate
        break
    fi
done
if [ -z "$python_command" ]; then
    echo 'Python 3.11+ required. Install Python and Node 24+ with your chosen package manager, then rerun.' >&2
    exit 2
fi
exec "$python_command" "$package_dir/install.py" "$@"
