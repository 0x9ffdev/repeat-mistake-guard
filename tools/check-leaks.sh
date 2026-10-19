#!/bin/sh
# Before every push: nothing personal or from a customer may end up in the template.
# The word list lives outside the repo (it would itself leak): $CREW_LEAK_WORDS or ~/.config/crew-framework/leak-words.txt
# One extended regex per line; an invalid line fails the check instead of passing it.
cd "$(dirname "$0")/.." || exit 1
WORDS="${CREW_LEAK_WORDS:-$HOME/.config/crew-framework/leak-words.txt}"
[ -f "$WORDS" ] || { echo "missing word list: $WORDS" >&2; exit 2; }
CLEAN=$(mktemp) || exit 2
trap 'rm -f "$CLEAN"' EXIT
tr -d '\r' < "$WORDS" | grep -v '^[[:space:]]*$' > "$CLEAN"
[ -s "$CLEAN" ] || { echo "empty word list: $WORDS" >&2; exit 2; }
grep -rniE -f "$CLEAN" --exclude-dir=.git --exclude=check-leaks.sh .
FILES=$?
# Commit authors and committers go public too; check the identity of the next commit as well.
{ git log --all --format='%an <%ae>%n%cn <%ce>' 2>/dev/null; git var GIT_AUTHOR_IDENT 2>/dev/null; } | sort -u | grep -niE -f "$CLEAN"
AUTHORS=$?
[ $FILES -gt 1 ] || [ $AUTHORS -gt 1 ] && { echo "check failed (bad pattern in $WORDS?)" >&2; exit 2; }
[ $FILES = 0 ] || [ $AUTHORS = 0 ] && { echo "LEAK: fix the lines above (files or commit identity)" >&2; exit 1; }
echo "clean"
