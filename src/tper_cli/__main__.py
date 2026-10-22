"""Entry point for ``python -m tper_cli`` and the ``tper`` console script."""

from __future__ import annotations

import sys

from tper_cli.cli import run


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
