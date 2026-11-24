"""Metro run. full: every metro source; quick (every three hours): open/awarded tenders, City tables, feeds.
Each part runs on its own: a part that fails leaves its previous output in place and is reported; the run fails only
if the money core cannot be built at all."""
import os, subprocess, sys, time, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
mode = sys.argv[1] if len(sys.argv) > 1 else "full"
py = lambda *a: [sys.executable, "-I", os.path.join(HERE, a[0]), *a[1:]]
steps = [("districts", py("districts.py"), True)] if mode == "full" or not os.path.exists(os.path.join(ROOT, "public/data/metro/districts.json")) else []
steps += [("money-fetch", py("fetch_money.py", *(["--refresh"] if mode == "full" else ["odp", "etenders", "--refresh"])), False),
          ("money-build", py("build_money.py"), True),
          ("feeds", py("feeds.py"), False),
          ("justice", py("justice.py", *(["--full"] if mode == "full" else [])), False),
          ("gazettes", py("gazettes.py", *([] if mode == "full" else [str(time.gmtime().tm_year)])), False)]
report = []
for name, cmd, core in steps:
    t = time.time(); r = subprocess.run(cmd)
    report.append({"step": name, "ok": r.returncode == 0, "seconds": round(time.time() - t)})
    print(f"== {name}: {'ok' if r.returncode == 0 else 'FAILED'} ({time.time() - t:.0f}s)", flush=True)
    if r.returncode and core: print("core step failed; stopping"); json.dump(report, open(os.path.join(ROOT, "public/data/metro/run.json"), "w")); sys.exit(1)
json.dump({"mode": mode, "steps": report}, open(os.path.join(ROOT, "public/data/metro/run.json"), "w"), indent=1)
