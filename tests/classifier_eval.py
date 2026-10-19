"""Correction detection against the real model (calls `claude -p --model haiku`, 12 calls). Run: python3 tests/classifier_eval.py /tmp/x"""
import json, os, subprocess, sys
G = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins", "guard", "scripts", "guard.py")
cases = [("you didn't run the tests before saying it works", 1), ("that's not what I asked, I wanted a CLI not a web app", 1),
 ("why did you delete my config file?", 1), ("next time put the docs in README, not a new file", 1),
 ("hmm, and what about Windows paths? you ignored them", 1), ("this is way too complicated again", 1),
 ("great, now add a --verbose flag", 0), ("yes, go with option B", 0), ("what does this regex do?", 0),
 ("leave it, it's not worth it", 0), ("can you also write a changelog entry?", 0), ("thanks, ship it", 0)]
ok = 0
for i, (msg, want) in enumerate(cases):
    home = os.path.join(sys.argv[1], f"c{i}"); os.makedirs(home, exist_ok=True)
    t = os.path.join(home, "t.jsonl")
    with open(t, "w") as f:
        f.write(json.dumps({"type":"user","message":{"content":"make the change"}})+"\n")
        f.write(json.dumps({"type":"assistant","message":{"content":[{"type":"text","text":"Done, the change is in place."}]}})+"\n")
        f.write(json.dumps({"type":"user","message":{"content":msg}})+"\n")
    out = subprocess.run([sys.executable, G, "stop"], input=json.dumps({"transcript_path": t}), capture_output=True, text=True,
                         env=dict(os.environ, GUARD_HOME=home)).stdout
    got = 1 if out.strip() else 0
    v = json.load(open(os.path.join(home, "verdicts.json")))
    model = "model" if any(not k.startswith("_") for k in v) else "KEYWORDS"
    ok += got == want
    print(("OK  " if got == want else "BAD ") + f"{model:8} want={want} got={got}  {msg}")
print(f"{ok}/{len(cases)}")
