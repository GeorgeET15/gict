"""Development command-line interface."""

import argparse

from gict import __version__


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="gict-dev",
        description="George's iPhone Copy Tool",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args()

    parser.error(
        "The portable device-access workflow is not implemented yet. "
        "This is a development package, not a backup command."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
