"""Allow ``python -m nodebridge`` from any working directory."""

from nodebridge.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
