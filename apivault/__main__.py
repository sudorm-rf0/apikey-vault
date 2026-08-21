"""Allow `python -m apivault` to work as `apivault`."""

from apivault.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
