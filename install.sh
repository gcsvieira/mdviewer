#!/bin/sh
set -eu

prefix=${MDVIEWER_PREFIX:-"$HOME/.local"}
archive=
configure_path=yes
while [ "$#" -gt 0 ]; do
    case "$1" in
        --archive) archive=${2:?--archive requires a file}; shift 2 ;;
        --prefix) prefix=${2:?--prefix requires a directory}; shift 2 ;;
        --no-path) configure_path=no; shift ;;
        --help)
            printf 'Usage: install.sh [--archive FILE] [--prefix DIRECTORY] [--no-path]\n'
            exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done

case $(uname -s) in
    Linux) ;;
    *) printf 'mdviewer currently supports Linux only.\n' >&2; exit 1 ;;
esac
for command in python3 tar sha256sum xvfb-run xauth kitten; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'Missing dependency: %s. See the README dependency commands.\n' "$command" >&2
        exit 1
    fi
done
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    sys.exit('mdviewer requires Python 3.10 or newer.')
try:
    import gi
    gi.require_foreign('cairo')
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
except (ImportError, ValueError) as error:
    sys.exit(f'Missing system GTK/WebKitGTK/PyGObject dependency: {error}. See README installation commands.')
PY

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
if [ -z "$archive" ]; then
    command -v curl >/dev/null 2>&1 || { printf 'curl is required.\n' >&2; exit 1; }
    architecture=$(uname -m)
    case "$architecture" in
        x86_64) ;;
        *) printf 'No release binary for %s; build from source with scripts/build.sh.\n' "$architecture" >&2; exit 1 ;;
    esac
    name="mdviewer-linux-$architecture.tar.gz"
    url="https://github.com/gcsvieira/mdviewer/releases/latest/download/$name"
    curl -fsSL "$url" -o "$temporary/$name"
    curl -fsSL "$url.sha256" -o "$temporary/$name.sha256"
    (cd "$temporary" && sha256sum -c "$name.sha256")
    archive="$temporary/$name"
fi
mkdir "$temporary/package"
tar -xzf "$archive" -C "$temporary/package"
application="$prefix/share/mdviewer"
mkdir -p "$prefix/bin" "$application"

# Keep the environment and user preferences during upgrades.
if [ ! -x "$application/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$application/venv"
fi
"$application/venv/bin/python" -m pip install --disable-pip-version-check \
    -r "$temporary/package/share/mdviewer/requirements.txt"
cp "$temporary/package/share/mdviewer/mdview.py" \
    "$temporary/package/share/mdviewer/mdview_settings.py" \
    "$temporary/package/share/mdviewer/requirements.txt" "$application/"
# Rename a new executable into place so running sessions can finish normally.
install -m 755 "$temporary/package/bin/mdview" "$prefix/bin/.mdview-install"
mv -f "$prefix/bin/.mdview-install" "$prefix/bin/mdview"

if [ "$configure_path" = yes ]; then
    python3 - "$prefix/bin" "${SHELL:-/bin/sh}" <<'PY'
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

directory = str(Path(sys.argv[1]).resolve())
shell = Path(sys.argv[2]).name
if shell == 'fish' and shutil.which('fish'):
    command = 'contains -- $argv[1] $fish_user_paths; or fish_add_path --universal --prepend -- $argv[1]'
    subprocess.run(['fish', '-c', command, directory], check=True)
else:
    filename = {'bash': '.bashrc', 'zsh': '.zshrc'}.get(shell, '.profile')
    path = Path.home() / filename
    existing = path.read_text() if path.exists() else ''
    line = f'export PATH={shlex.quote(directory)}:"$PATH"'
    if line not in existing:
        with path.open('a') as file:
            file.write('\n# mdviewer executable\n' + line + '\n')
PY
fi
printf '\nInstalled %s/bin/mdview\n' "$prefix"
printf 'Settings preserved at ~/.config/mdviewer/settings.json\n'
printf 'Run: mdview (restart your terminal if PATH has not refreshed).\n'
