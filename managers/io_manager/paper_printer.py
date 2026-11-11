"""PaperPrinter: prints text inside a frame so it looks a bit like reading
your work on paper while also looking at a command console."""

import textwrap
from typing import Any


class PaperPrinter:
    """Prints text inside a frame so it looks a bit like reading your work on
    paper while also looking at a command console."""

    WIDTH = 110

    def __init__(self, width: int = WIDTH) -> None:
        self._width = width

    def print_on_paper(
        self,
        lines: list[str],
        title: str = "REPORT",
        footer: str = "End of report",
        width: int | None = None,
    ) -> None:
        """Print a list of text lines inside a paper-style frame."""
        width = width or self._width
        inner = width - 4  # usable space between "| " and " |"

        def row(text: str = "") -> None:
            print(f"| {text:<{inner}} |")

        print()
        print("+" + "-" * (width - 2) + "+")
        row(title.center(inner))
        row("=" * inner)
        row()

        for text in lines:
            stripped = text.lstrip()
            indent = " " * (len(text) - len(stripped))
            # Bullets get a hanging indent so wrapped lines align under the text
            if stripped.startswith("- "):
                indent += "  "
            wrapped = textwrap.wrap(text, width=inner, subsequent_indent=indent) or [""]
            for piece in wrapped:
                row(piece)

        row()
        row("-" * inner)
        row(footer.center(inner))
        row()
        print(("\\/" * width)[:width])  # torn paper edge

    def format_pairs(
        self, data: Any, width: int | None = None, indent: str = ""
    ) -> list[str]:
        """Turn a dict into aligned 'key : value' lines with a hanging indent."""
        width = width or self._width
        inner = width - 4 - len(indent)
        if not data:
            return ["(no data)"]
        key_w = max((len(str(k)) for k in data), default=0)
        lines = []
        for key, value in data.items():
            label = f"{str(key):<{key_w}} : "
            hang = " " * len(label)
            wrapped = textwrap.wrap(str(value), width=inner - len(label)) or [""]
            lines.append(indent + label + wrapped[0])
            lines.extend(indent + hang + extra for extra in wrapped[1:])
        return lines
