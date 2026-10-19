"""Example console entry point."""

from __future__ import annotations

import argparse

from hello_pkg import greeting


def main() -> int:
    parser = argparse.ArgumentParser(description="Print a greeting from an installed Python package.")
    parser.add_argument("name", nargs="?", default="developer", help="name to greet")
    args = parser.parse_args()
    print(greeting(args.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
