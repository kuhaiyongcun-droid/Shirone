#!/bin/sh
# Manual Linux helper. Does not upload, reload nginx, or delete any release.
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Usage: sh switch-release.sh RELEASE_ID' >&2
    exit 2
fi
release_id=$1
case "$release_id" in
    ''|*[!A-Za-z0-9_-]*) printf '%s\n' 'Invalid release id.' >&2; exit 2 ;;
esac

site_root=/srv/kuhai
releases_root=$site_root/releases
release_root=$releases_root/$release_id
target_root=$release_root/dist
if [ ! -d "$target_root" ]; then
    printf '%s\n' 'Release dist directory is missing.' >&2
    exit 1
fi
actual_releases=$(realpath -e "$releases_root")
actual_target=$(realpath -e "$target_root")
if [ "$actual_releases" != "$releases_root" ] || [ "$actual_target" != "$target_root" ]; then
    printf '%s\n' 'Release paths must be real directories under /srv/kuhai/releases.' >&2
    exit 1
fi
for required in index.html blog/index.html 404.html; do
    if [ ! -f "$target_root/$required" ] || [ -L "$target_root/$required" ]; then
        printf 'Missing regular entry file: %s\n' "$required" >&2
        exit 1
    fi
done
if [ -e "$site_root/current" ] && [ ! -L "$site_root/current" ]; then
    printf '%s\n' 'Refusing to replace a non-symlink current path.' >&2
    exit 1
fi
previous_target='(first release)'
if [ -L "$site_root/current" ]; then
    previous_target=$(realpath -e "$site_root/current")
    case "$previous_target" in
        "$releases_root"/*/dist) ;;
        *) printf '%s\n' 'Existing current points outside managed release dist directories.' >&2; exit 1 ;;
    esac
fi
next_link=$site_root/.current-next-$release_id-$$
if [ -e "$next_link" ] || [ -L "$next_link" ]; then
    printf '%s\n' 'Temporary switch path already exists; nothing changed.' >&2
    exit 1
fi
ln -s "$target_root" "$next_link"
trap 'if [ -L "$next_link" ]; then rm -- "$next_link"; fi' EXIT
trap 'exit 1' HUP INT TERM
# Both links live in the same directory/filesystem; GNU mv -T renames the link.
mv -Tf -- "$next_link" "$site_root/current"
printf 'Previous: %s\nCurrent:  %s\n' "$previous_target" "$target_root"
printf '%s\n' 'Release pointer switched. Run the HTTP checks; no server reload was executed.'
