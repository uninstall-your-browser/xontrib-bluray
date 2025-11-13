from pathlib import Path

from prompt_toolkit.styles import Style

STATE_FILE = Path("~/.local/state/bluray").expanduser()
style = Style.from_dict(
    {
        "dialog.body": "fg:white bg:ansidefault",
        "frame.label": "royalblue",
        "list.dir": "#9595ea",
        "list.dir.hidden": "#6464a5",
        "list.thisdir": "MediumSeaGreen",
        "list.file": "darkgray",
        "list.file.hidden": "gray",
        # "list.selected": "orangered",
        "list.selected": "bg:white fg:black",
    }
)
