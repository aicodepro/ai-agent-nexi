"""Entry point for the vision subprocess: python -m vision.runner [hand|eye]."""

import sys


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "hand"
    if mode == "eye":
        from vision.eye import run
    else:
        from vision.hand import run
    run()


if __name__ == "__main__":
    main()
