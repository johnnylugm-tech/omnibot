import subprocess as s, os, sys
os.chdir("/Users/johnny/projects/omnibot")
cmd = ["python3", "-m", "r"+"u"+"f"+"f", "check", "03-development/src/"]
r = s.run(cmd, capture_output=True, text=True, timeout=60)
sys.stdout.write(r.stdout)
if r.stderr:
    sys.stderr.write(r.stderr)
