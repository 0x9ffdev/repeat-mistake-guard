---
name: retro
description: Guard retro – write down what the user corrected so it does not happen again; when the same mistake comes back, turn the lesson into a check a hook enforces. Use on /guard:retro, when the stop hook asks for it, and whenever the user corrects your work ("that's wrong", "again?", "next time do…").
---
# Retro

The tool is `python3 ~/.claude/guard/lessons.py` (the plugin's hooks create that link on first run; if it is missing, use the `scripts/lessons.py` next to this skill).

1. **Name the lesson** in one line: what you will do differently, and why. Only from the user's correction or a verified result, never a guess. Nothing to learn (it was a question or a new task) → tell the user `Retro: no lesson – <why>` and stop.
2. **Write it:** `lessons.py add "<lesson>" --project <folder name>`.
   - `Lesson written` → done. Tell the user the lesson in one sentence.
   - `ALREADY KNOWN` (exit 3) → it is a **repeat mistake**: the text already failed once, another line will fail again. Go to 3. Only if the match is clearly a different topic, re-run with `--new`.
3. **Turn it into a check.** Find the tool call that the mistake always goes through and add a rule the PreToolUse hook enforces:
   `lessons.py check add --id <short-id> --tool Bash --field command --pattern "<regex>" --message "<why, and what to do instead>" --test "<a real command that must be stopped>"`
   - `--tool Bash --field command` for commands, `--tool Edit|Write --field file_path` for files, `--tool "*"` matches the whole input of any tool.
   - `--unless "<regex>"` for the correct form (e.g. stop `git push` to main, unless `--dry-run`).
   - `--test` must match, or the check is refused. Also make sure the correct way still passes (run `check list` and read the pattern once more).
   - Then log it: `lessons.py repeat "<lesson>" --check <short-id>`.
   - No tool call to catch (tone, wording, a judgment)? Make the lesson a `Done =` step in the relevant skill or CLAUDE.md that you must show the result of, and log `lessons.py repeat "<lesson>" --proposed "<what you changed or the user should add>"`.
4. Tell the user in one sentence: the lesson, or the repeat mistake and its new check.

`lessons.py report` shows how it is going: new lessons, repeat mistakes, how many got a check. Lessons, checks and the log are plain files in `~/.claude/guard/`; the user may edit or delete them.
