#!/usr/bin/env python3
"""Lessons and checks: a lesson is written once; a repeat mistake becomes a check, not another line.

  lessons.py search "text"                       similar lessons already on file
  lessons.py add "text" [--project P] [--new]    write a lesson; if a similar one exists, refuse (exit 3)
  lessons.py repeat "text" --check <id>          log a repeat mistake fixed by check <id> (see `check add`)
  lessons.py repeat "text" --proposed "what"     log a repeat mistake whose fix needs the user (e.g. a CI step)
  lessons.py check add --id ID --tool Bash --field command --pattern REGEX --message "why" --test "sample"
                                                 add a check the PreToolUse hook enforces; --test must match
  lessons.py check list                          all checks
  lessons.py report [--days 7]                   new lessons, repeat mistakes, how many got a check

Data lives in $GUARD_HOME (default ~/.claude/guard): LESSONS.md, checks.json, log.jsonl. Plain files, edit freely.
"""
import datetime
import json
import os
import re
import sys
import unicodedata

HOME = os.environ.get("GUARD_HOME") or os.path.expanduser("~/.claude/guard")
LESSONS = os.path.join(HOME, "LESSONS.md")
CHECKS = os.path.join(HOME, "checks.json")
LOG = os.path.join(HOME, "log.jsonl")
THRESHOLD, MIN_SHARED = 0.34, 3
TOOLS = {"Bash": "command", "Edit": "file_path", "Write": "file_path", "*": "input"}
STOP = set("""this that with from when then than they them their there have will would should could
must always never into only also just about after before because every each other which while
where what your user does doing done make made using used like more most less some such very""".split())


def plain(text):
    """Lower case without diacritics, so "přidej" and "pridej" are the same word."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def one_line(text):
    """Lessons are one line each, and "·" separates date · project · text."""
    return re.sub(r"\s+", " ", text.replace("·", "-")).strip()


def stems(text):
    text = re.sub(r"^\s*-\s*\d{4}-\d\d-\d\d\s*·[^·]*·", "", text)  # date and project are not content
    words = re.findall(r"[a-z0-9]+", plain(text))
    return {w[:5] for w in words if len(w) >= 4 and w not in STOP}


def lessons():
    try:
        return [r for r in open(LESSONS, encoding="utf-8").read().splitlines() if r.startswith("- ")]
    except OSError:
        return []


def similar(text, n=5):
    a, found = stems(text), []
    for line in lessons():
        b = stems(line)
        shared = a & b
        if a and b and len(shared) >= MIN_SHARED:
            found.append((len(shared) / min(len(a), len(b)), line))
    return sorted(found, reverse=True)[:n]


def log(**entry):
    entry["date"] = datetime.date.today().isoformat()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_checks():
    try:
        checks = json.load(open(CHECKS, encoding="utf-8"))
        return checks if isinstance(checks, list) else []
    except (OSError, ValueError):
        return []


def flatten(value):
    """All strings in a tool input, one per line: what a `--tool "*"` check is matched against."""
    if isinstance(value, dict):
        return "\n".join(flatten(v) for v in value.values())
    if isinstance(value, list):
        return "\n".join(flatten(v) for v in value)
    return value if isinstance(value, str) else json.dumps(value)


def write_atomic(path, data):
    """The PreToolUse hook reads checks.json on every tool call: never let it see a half-written file."""
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def add(text, project, force):
    hits = [h for h in similar(text) if h[0] >= THRESHOLD]
    if hits and not force:
        print("ALREADY KNOWN: this is a repeat mistake, not a new lesson.")
        for score, line in hits[:3]:
            print(f"  {score:.2f}  {line[:220]}")
        print("\nDo not add another line; the text already failed once. Add a check instead:\n"
              '  lessons.py check add --id <id> --tool Bash --field command --pattern "<regex>" '
              '--message "<why>" --test "<a command that must be stopped>"\n'
              f'  lessons.py repeat "{text}" --check <id>\n'
              'No tool call to catch (e.g. it is about tone)? Make the lesson a "Done =" step in the skill or '
              'CLAUDE.md, or log --proposed "<what the user should add>". Really something different? Re-run with --new.')
        sys.exit(3)
    line = f"- {datetime.date.today().isoformat()} · {one_line(project)} · {one_line(text)}"
    with open(LESSONS, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    log(type="new", project=project, text=text)
    print(f"Lesson written to {LESSONS}.")


def check_add(args):
    cid, tool, field = opt(args, "--id"), opt(args, "--tool", "Bash"), opt(args, "--field")
    pattern, message, sample = opt(args, "--pattern"), opt(args, "--message"), opt(args, "--test")
    field = field or TOOLS.get(tool)
    if not (cid and pattern and message and sample and field):
        sys.exit("Need --id, --pattern, --message, --test and --field (Bash → command, Edit/Write → file_path).")
    if tool not in TOOLS:
        sys.exit(f"--tool must be one of {', '.join(TOOLS)}.")
    unless = opt(args, "--unless")
    try:
        rx, rx_unless = re.compile(pattern), re.compile(unless) if unless else None
    except re.error as e:
        sys.exit(f"Bad regex: {e}")
    if not rx.search(sample):
        sys.exit("The pattern does not match --test, so the check would never fire. Fix the pattern.")
    if rx_unless and rx_unless.search(sample):
        sys.exit("--unless matches --test too, so the check would never fire. Narrow --unless.")
    checks = [c for c in load_checks() if c.get("id") != cid]
    entry = {"id": cid, "tool": tool, "field": field, "pattern": pattern, "message": message,
             "added": datetime.date.today().isoformat()}
    if unless:
        entry["unless"] = unless
    checks.append(entry)
    write_atomic(CHECKS, checks)
    print(f"Check {cid} added; the PreToolUse hook enforces it from the next tool call.")


def repeat(text, args):
    cid, proposed = opt(args, "--check"), opt(args, "--proposed")
    if cid and not any(c.get("id") == cid for c in load_checks()):
        sys.exit(f"No check with id {cid}. Add it first with `lessons.py check add`.")
    if not (cid or proposed):
        sys.exit('Need --check <id> (a check you added) or --proposed "<what the user should add>".')
    log(type="repeat", text=text, check=cid, proposed=proposed)
    print("Repeat mistake logged.")


def report(days):
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    try:
        entries = [json.loads(r) for r in open(LOG, encoding="utf-8") if r.strip()]
    except OSError:
        entries = []
    recent = [e for e in entries if e["date"] >= since]
    new = [e for e in recent if e["type"] == "new"]
    rep = [e for e in recent if e["type"] == "repeat"]
    checked = [e for e in rep if e.get("check")]
    print(f"Last {days} days: new lessons {len(new)}, repeat mistakes {len(rep)}, "
          f"fixed by a check {len(checked)}, waiting for you {len(rep) - len(checked)}. "
          f"Lessons on file {len(lessons())}, checks enforced {len(load_checks())}.")
    for e in rep:
        print(f"  repeat · {e['date']} · {e['text'][:100]} → {e.get('check') or 'proposed: ' + (e.get('proposed') or '?')}")


def main():
    os.makedirs(HOME, exist_ok=True)
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "search" and len(a) == 2:
        for score, line in similar(a[1]):
            print(f"{score:.2f}  {line[:220]}")
    elif a[0] == "add" and len(a) >= 2:
        add(a[1], opt(a, "--project", "-"), "--new" in a)
    elif a[0] == "repeat" and len(a) >= 2:
        repeat(a[1], a)
    elif a[:2] == ["check", "add"]:
        check_add(a)
    elif a[:2] == ["check", "list"]:
        for c in load_checks():
            print(f"{c['id']}: {c['tool']}.{c['field']} ~ /{c['pattern']}/ → {c['message']}")
    elif a[0] == "report":
        report(int(opt(a, "--days", "7")))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
