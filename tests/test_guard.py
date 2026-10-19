"""Tests for the guard plugin. Run: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "guard", "scripts")
GUARD, LESSONS = os.path.join(SCRIPTS, "guard.py"), os.path.join(SCRIPTS, "lessons.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.fake = os.path.join(self.home, "fake.py")  # classifier stand-in: answers from $FAKE_ANSWER
        with open(self.fake, "w") as f:
            f.write("import os,sys\nsys.exit(int(os.environ.get('FAKE_EXIT','0'))) if os.environ.get('FAKE_EXIT') "
                    "else print(os.environ.get('FAKE_ANSWER','NO'))\n")
        self.env = dict(os.environ, GUARD_HOME=self.home, GUARD_CLASSIFIER=f"{sys.executable} {self.fake}")
        self.env.pop("GUARD_CLASSIFYING", None)

    def tearDown(self):
        self.tmp.cleanup()

    def lessons(self, *args):
        return subprocess.run([sys.executable, LESSONS, *args], env=self.env, capture_output=True, text=True)

    def hook(self, mode, data, **env):
        p = subprocess.run([sys.executable, GUARD, mode], input=json.dumps(data), env=dict(self.env, **env),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if p.stdout.strip() else None

    def transcript(self, *entries):
        path = os.path.join(self.home, "t.jsonl")
        with open(path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        return {"transcript_path": path}


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(text="", tool=None):
    content = [{"type": "text", "text": text}] if text else []
    if tool:
        content.append({"type": "tool_use", "id": tool[0], "name": "Bash", "input": {"command": tool[1]}})
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def result(tid, error=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": "ok", "is_error": error}]}}


class Lessons(Base):
    def test_new_then_repeat(self):
        self.assertEqual(self.lessons("add", "Run the mobile layout test before saying the page is done").returncode, 0)
        p = self.lessons("add", "Page was done without the mobile layout test again")
        self.assertEqual(p.returncode, 3)
        self.assertIn("ALREADY KNOWN", p.stdout)
        self.assertEqual(self.lessons("add", "Ask before deleting production database rows").returncode, 0)

    def test_new_flag_overrides(self):
        self.lessons("add", "Run the mobile layout test before saying the page is done")
        self.assertEqual(self.lessons("add", "Mobile layout test page done differently", "--new").returncode, 0)

    def test_check_must_match_sample(self):
        p = self.lessons("check", "add", "--id", "x", "--pattern", "git push.*main", "--message", "m", "--test", "ls")
        self.assertNotEqual(p.returncode, 0)
        p = self.lessons("check", "add", "--id", "x", "--pattern", "(", "--message", "m", "--test", "(")
        self.assertIn("Bad regex", p.stderr)

    def test_repeat_needs_existing_check(self):
        self.assertNotEqual(self.lessons("repeat", "t", "--check", "nope").returncode, 0)
        self.assertNotEqual(self.lessons("repeat", "t").returncode, 0)
        self.assertEqual(self.lessons("repeat", "t", "--proposed", "CI step").returncode, 0)
        self.assertIn("repeat mistakes 1", self.lessons("report").stdout)


class ReviewFixes(Base):
    def test_unless_must_not_match_sample(self):
        p = self.lessons("check", "add", "--id", "u", "--pattern", "git push", "--unless", "push", "--message", "m",
                         "--test", "git push main")
        self.assertIn("--unless matches", p.stderr)
        p = self.lessons("check", "add", "--id", "u", "--pattern", "x", "--unless", "(", "--message", "m", "--test", "x")
        self.assertIn("Bad regex", p.stderr)

    def test_czech_repeat_is_found(self):
        self.lessons("add", "Před nasazením vždycky spustit testy na mobilu")
        self.assertEqual(self.lessons("add", "Pred nasazenim spustit testy na mobilu").returncode, 3)  # no diacritics
        self.assertEqual(self.lessons("add", "Zase nasazení, aniž by se spustily testy na mobilu").returncode, 3)

    def test_one_line_per_lesson(self):
        self.lessons("add", "Test mobile\n- 2026-01-01 · x · fake", "--project", "a·b")
        lines = [r for r in open(os.path.join(self.home, "LESSONS.md")).read().splitlines() if r]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].count("·"), 2)

    def test_retro_commands_pass_their_own_checks(self):
        self.lessons("check", "add", "--id", "np", "--pattern", r"git push\b.*\bmain\b", "--message", "m",
                     "--test", "git push origin main")
        for cmd in ['python3 ~/.claude/guard/lessons.py repeat "never git push to main" --check np',
                    'python3 -I /x/lessons.py check add --id np --pattern "git push.*main" --test "git push origin main"']:
            self.assertIsNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": cmd}}), cmd)
        for cmd in ['python3 lessons.py add "x"; git push origin main', 'python3 lessons.py add "$(git push origin main)"',
                    'python3 lessons.py add x && git push origin main', 'bash -c "git push origin main" lessons.py']:
            self.assertIsNotNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": cmd}}), cmd)

    def test_any_tool_matches_raw_text(self):
        self.lessons("check", "add", "--id", "cz", "--tool", "*", "--pattern", 'produkční "db"', "--message", "m",
                     "--test", 'produkční "db"')
        self.assertIsNotNone(self.hook("pre", {"tool_name": "mcp__x", "tool_input": {"q": ['use produkční "db"']}}))

    def test_keyword_fallback_is_narrow(self):
        for msg in ["do the same again for the footer", "what's wrong with the build?"]:
            self.assertIsNone(self.hook("stop", self.transcript(user(msg)), FAKE_EXIT="1"), msg)
        for msg in ["zase jsi to rozbil", "Příště to piš kratší", "you forgot the tests"]:
            self.assertIsNotNone(self.hook("stop", self.transcript(user(msg)), FAKE_EXIT="1"), msg)


class Pre(Base):
    def add_check(self):
        p = self.lessons("check", "add", "--id", "no-main-push", "--pattern", r"git push\b.*\bmain\b",
                         "--unless", "--dry-run", "--message", "push to a branch", "--test", "git push origin main")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_denies_matching_command(self):
        self.add_check()
        out = self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("no-main-push", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_allows_other_and_unless(self):
        self.add_check()
        self.assertIsNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": "git push origin feature"}}))
        self.assertIsNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": "git push --dry-run origin main"}}))
        self.assertIsNone(self.hook("pre", {"tool_name": "Edit", "tool_input": {"file_path": "main.py"}}))

    def test_file_and_any_tool(self):
        self.lessons("check", "add", "--id", "env", "--tool", "Edit", "--pattern", r"\.env$", "--message", "m",
                     "--test", "app/.env")
        self.lessons("check", "add", "--id", "any", "--tool", "*", "--pattern", "prod-db", "--message", "m",
                     "--test", "x prod-db")
        self.assertIsNotNone(self.hook("pre", {"tool_name": "Edit", "tool_input": {"file_path": "app/.env"}}))
        self.assertIsNotNone(self.hook("pre", {"tool_name": "mcp__sql__query", "tool_input": {"db": "prod-db"}}))

    def test_broken_checks_file_is_ignored(self):
        with open(os.path.join(self.home, "checks.json"), "w") as f:
            json.dump([{"id": "b", "tool": "Bash", "field": "command", "pattern": "("}], f)
        self.assertIsNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": "("}}))
        with open(os.path.join(self.home, "checks.json"), "w") as f:
            f.write("not json")
        self.assertIsNone(self.hook("pre", {"tool_name": "Bash", "tool_input": {"command": "ls"}}))


class Stop(Base):
    def test_correction_without_retro_blocks(self):
        t = self.transcript(user("build the page"), assistant("Done."), user("you didn't test it on mobile"))
        out = self.hook("stop", t, FAKE_ANSWER="CORRECTION")
        self.assertEqual(out["decision"], "block")
        self.assertIn("lessons.py", out["reason"])

    def test_not_a_correction(self):
        t = self.transcript(user("build the page"), assistant("Done."), user("now add a footer"))
        self.assertIsNone(self.hook("stop", t, FAKE_ANSWER="NO"))

    def test_successful_retro_clears(self):
        t = self.transcript(user("you forgot mobile again"),
                            assistant("Writing it.", ("t1", "python3 ~/.claude/guard/lessons.py add \"test mobile\"")),
                            result("t1"), assistant("Lesson written."))
        self.assertIsNone(self.hook("stop", t, FAKE_ANSWER="CORRECTION"))

    def test_failed_retro_does_not_count(self):
        t = self.transcript(user("you forgot mobile again"),
                            assistant("", ("t1", "python3 ~/.claude/guard/lessons.py add \"test mobile\"")),
                            result("t1", error=True), assistant("It said already known."))
        self.assertEqual(self.hook("stop", t, FAKE_ANSWER="CORRECTION")["decision"], "block")

    def test_mentioning_lessons_py_is_not_a_retro(self):
        t = self.transcript(user("that's wrong"), assistant("", ("t1", "cat lessons.py")), result("t1"))
        self.assertEqual(self.hook("stop", t, FAKE_ANSWER="CORRECTION")["decision"], "block")

    def test_no_lesson_escape(self):
        t = self.transcript(user("why is it blue?"), assistant("Retro: no lesson – it was a question."))
        self.assertIsNone(self.hook("stop", t, FAKE_ANSWER="CORRECTION"))
        t = self.transcript(user("why is it blue?"))
        self.assertIsNone(self.hook("stop", dict(t, last_assistant_message="Retro: no lesson – a question"),
                                    FAKE_ANSWER="CORRECTION"))

    def test_correction_before_retro_is_settled(self):
        t = self.transcript(user("wrong file"), assistant("", ("t1", "python3 lessons.py add \"x\"")), result("t1"),
                            user("thanks, now the footer"))
        self.assertIsNone(self.hook("stop", t, FAKE_EXIT="1"))  # keywords: only the settled message matches

    def test_model_down_falls_back_to_keywords(self):
        t = self.transcript(user("that's wrong again"))
        self.assertEqual(self.hook("stop", t, FAKE_EXIT="1")["decision"], "block")
        t = self.transcript(user("add a footer"))
        self.assertIsNone(self.hook("stop", t, FAKE_EXIT="1"))

    def test_never_loops(self):
        t = self.transcript(user("that's wrong"))
        self.assertIsNone(self.hook("stop", dict(t, stop_hook_active=True), FAKE_ANSWER="CORRECTION"))

    def test_ignores_tool_output_and_meta(self):
        t = self.transcript({"type": "user", "isMeta": True, "message": {"content": "wrong"}},
                            user("<command-name>/clear</command-name>"), result("x"))
        self.assertIsNone(self.hook("stop", t, FAKE_ANSWER="CORRECTION"))

    def test_verdict_cached(self):
        t = self.transcript(user("you didn't test it"))
        self.hook("stop", t, FAKE_ANSWER="CORRECTION")
        self.assertEqual(self.hook("stop", t, FAKE_EXIT="1")["decision"], "block")  # cache, not keywords


class Start(Base):
    def test_lessons_in_context(self):
        self.assertIsNone(self.hook("start", {}))
        self.lessons("add", "Run the mobile layout test before saying done")
        out = self.hook("start", {})
        self.assertIn("mobile layout", out["hookSpecificOutput"]["additionalContext"])

    def test_links_stable_lessons_path(self):
        self.hook("start", {})
        self.assertEqual(os.path.realpath(os.path.join(self.home, "lessons.py")), os.path.realpath(LESSONS))


if __name__ == "__main__":
    unittest.main()
