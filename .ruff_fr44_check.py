import subprocess
result = subprocess.run(
    ["/Users/johnny/projects/omnibot/.venv/bin/ruff", "check", "/Users/johnny/projects/omnibot/03-development/src/"],
    capture_output=True,
    text=True,
)
with open("/Users/johnny/projects/omnibot/.ruff_fr44_out.txt", "w") as f:
    f.write("STDOUT:\n" + result.stdout + "\n")
    f.write("STDERR:\n" + result.stderr + "\n")
    f.write("RC: " + str(result.returncode) + "\n")
