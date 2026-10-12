#!/bin/sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=${MDVIEWER_BUILD_DIR:-"$repository/dist"}
architecture=$(uname -m)
package="$output/mdviewer-linux-$architecture"
mkdir -p "$package/bin" "$package/share/mdviewer"
"${CC:-cc}" -std=c11 -Os -Wall -Wextra -Werror -s \
    "$repository/native/launcher.c" -o "$package/bin/mdview"
cp "$repository/mdview.py" "$repository/mdview_settings.py" \
    "$repository/requirements.txt" "$package/share/mdviewer/"
archive="mdviewer-linux-$architecture.tar.gz"
tar -C "$package" -czf "$output/$archive" bin share
(cd "$output" && sha256sum "$archive" > "$archive.sha256")
printf 'Built %s\n' "$output/$archive"
