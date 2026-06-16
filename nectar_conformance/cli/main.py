"""cliff application entry point."""

from __future__ import annotations

import sys

from cliff.app import App
from cliff.commandmanager import CommandManager

from nectar_conformance import __version__


class ConformanceApp(App):
    def __init__(self):
        super().__init__(
            description="Conformance checker for Nectar puppet-managed cloud sites",
            version=__version__,
            command_manager=CommandManager("nectar_conformance.cli"),
            deferred_help=True,
        )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    return ConformanceApp().run(argv)


if __name__ == "__main__":
    sys.exit(main())
