# Repeat-mistake guard

A Claude Code plugin. Correct Claude once and it writes down a lesson. Make the same mistake twice and the lesson becomes a check that a hook enforces, because a second line of text would fail the same way the first one did.

```
you:    "You pushed straight to main again!"
guard:  ALREADY KNOWN – this is a repeat mistake, not a new lesson.
claude: added check no-push-main (blocks git push … main), logged the repeat
next session:
claude: git push origin HEAD:main
hook:   denied – guard check no-push-main: never push to main, push a feature branch
```

## Install

```
/plugin marketplace add 0x9ffdev/repeat-mistake-guard
/plugin install guard@repeat-mistake-guard
```

Restart Claude Code. Nothing to configure. Requires `python3`.

## How it works

1. **Notices corrections.** When Claude stops, a hook reads your last messages and asks Haiku (via your own `claude -p`) whether one is feedback on the work: "that's wrong", "you didn't test mobile", "next time keep it shorter", "wait, I only wanted a list". A new task, a question or "yes, ship it" is not. If the model is unavailable, keywords decide.
2. **Asks for the lesson.** If you corrected Claude and no lesson was written since, the hook stops Claude from finishing until it writes one (`lessons.py add`) or says `Retro: no lesson – <why>`. It never blocks twice in a row.
3. **Refuses duplicates.** `lessons.py add` compares the lesson with the ones on file. A similar one means the text already failed, so it refuses (exit 3) and asks for a check instead.
4. **Turns repeats into checks.** Claude adds a rule to `checks.json` (tool, field, regex, optional `unless`, message). The rule must match a real example of the mistake, or it is refused. A PreToolUse hook denies every matching tool call from then on.
5. **Loads lessons.** At session start, the lessons go into Claude's context.

`/guard:retro` runs the same steps by hand. `python3 ~/.claude/guard/lessons.py report` shows the numbers: new lessons, repeat mistakes, how many got a check.

## Measured

- Correction detection with Haiku: 12/12 on a mixed set of 6 corrections and 6 non-corrections (`tests/classifier_eval.py`; your own wording may differ).
- End-to-end on a clean install, three scenarios: a lesson is written and used in a new session (.txt → .md notes); a lesson "never push to main" is ignored once (text failed), the second correction turns it into a check, and the check blocks the next push.
- 27 unit tests: `python3 -m unittest discover tests`.

This comes out of a longer setup where one person works with a crew of Claude Code roles. There, 19 of 35 rules are now enforced by hooks instead of text.

## What it touches

- Reads the session transcript (the hook input) and `~/.claude/guard/`. Writes only to `~/.claude/guard/`: `LESSONS.md`, `checks.json`, `log.jsonl`, a verdict cache, and a `lessons.py` link. Set `GUARD_HOME` to move it.
- Makes no network calls of its own and sends no telemetry. The only outside call is your local `claude -p --model haiku` with the message being judged and the end of Claude's previous reply. It runs in an empty folder, without tools or MCP.
- Everything is plain text. Edit or delete lessons and checks freely; deleting `~/.claude/guard/` resets the plugin.

## Limits

- A check catches a tool call (a command, a file path, a tool input). A mistake in tone or judgment cannot be caught by a regex. For those, the retro turns the lesson into a `Done =` step in a skill or CLAUDE.md and logs it as proposed.
- Similarity is word overlap, not meaning. Use `--new` when two lessons share words but differ in substance.
- Checks are regexes Claude writes. Review `checks.json` now and then (`lessons.py check list`).

MIT licence.
