"""Generic tool runner — invokes a library by import name from sys.argv."""
import importlib
import sys


def main():
    if len(sys.argv) < 3:
        print("usage: load_lib.py <module> <entrypoint_fn> [args...]", file=sys.stderr)
        sys.exit(2)

    sys.path.insert(0, "/Users/johnny/Library/Python/3.9/lib/python/site-packages")

    module_name = sys.argv[1]
    fn_name = sys.argv[2]

    module = importlib.import_module(module_name)
    fn = getattr(module, fn_name)

    sys.argv = [module_name] + sys.argv[3:]
    fn()


if __name__ == "__main__":
    main()
