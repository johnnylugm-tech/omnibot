import subprocess
r = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
    cwd="/Users/johnny/projects/omnibot",
)
out_path = "/Users/johnny/projects/omnibot/.fr96_ruff_output.txt"
with open(out_path, "w") as f:
    f.write("STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr + "\nEXIT:" + str(r.returncode))
print("done exit=", r.returncode)