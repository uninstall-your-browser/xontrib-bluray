from pathlib import Path

from prompt_toolkit.styles import Style

STATE_FILE = Path("~/.local/state/bluray").expanduser()
style = Style.from_dict(
    {
        "dialog.body": "fg:white bg:ansidefault",
        "frame.label": "royalblue",
        "list.dir": "#9595ea",
        "list.dir.hidden": "#4c4c99",
        "list.thisdir": "MediumSeaGreen",
        "list.file": "darkgray",
        "list.file.hidden": "#666666",
        # "list.selected": "orangered",
        "list.selected": "bg:white fg:black",
        "selection-mode": "SpringGreen",
        "text-area": "bg:ansidefault",
        "text-area.focused": "white",
        "filter-hint": "darkgray underline",
        "bottom-bar.disabled": "grey italic",
        "bottom-bar.filtering": "bg:crimson",
        "bottom-bar.dotfiles": "fg:white",
    }
)
MAX_HEIGHT = 20
MAX_CONTENT_HEIGHT = MAX_HEIGHT - 3
MIN_WIDTH = 40
