import os
from asyncio import ensure_future
from pathlib import Path
from threading import BoundedSemaphore

from prompt_toolkit.application import get_app
from prompt_toolkit.key_binding import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style, merge_styles
from xonsh.built_ins import XonshSession
from xonsh.events import events
from xonsh.prompt.base import PromptFields
from xonsh.shells.ptk_shell import PromptToolkitShell

from xontrib_bluray import dialog
from xontrib_bluray.path_picker import PathPickerDialog

style = Style.from_dict(
    {
        "dialog.body": "fg:white bg:ansidefault",
        "frame.label": "royalblue",
        "list.dir": "#9595ea",
        "list.dir.hidden": "#5555dd",
        "list.thisdir": "crimson",
        "list.file": "darkgray",
        "list.file.hidden": "gray",
        "list.selected": "orangered",
    }
)

open_sem = BoundedSemaphore()


def _load_xontrib_(xsh: XonshSession, **_):
    @events.on_ptk_create
    def custom_keybindings(bindings, **kw):
        added_styles = False

        @bindings.add(Keys.ControlK)
        @bindings.add("c-y")
        def show_pathpicker(event: KeyPressEvent):
            nonlocal added_styles
            if not added_styles:
                get_app().style = merge_styles([get_app().style, style])
                added_styles = True

            async def coro():
                nonlocal event

                if open_sem.acquire(blocking=False):
                    try:
                        new_dir: Path | None = await dialog.show_as_float(
                            PathPickerDialog(), height=20, top=0
                        )

                        if not new_dir:
                            return

                        # Change the working directory to the new one
                        os.chdir(new_dir)

                        # As we have just fucked with the working directory in a way the shell does not expect us to, we need to
                        # update the prompt message and re-render it manually.
                        shell: PromptToolkitShell = xsh.shell.shell
                        prompt_fields: PromptFields = shell.prompt_formatter.fields
                        # Delete the prompt formatter's cache, it is out of date now.
                        prompt_fields.reset()
                        # Update the shell environment with the new PWD.
                        xsh.env["PWD"] = str(new_dir)
                        # Re-format the prompt with the new PWD
                        shell.prompter.message = shell.prompt_tokens()
                        # Finally, re-render the prompt.
                        event.cli.renderer.erase()
                    finally:
                        open_sem.release()

            ensure_future(coro())


def run():
    """
    Start a xonsh shell from python for pycharm debugging
    """
    from xonsh.built_ins import XSH
    from xonsh.main import setup

    print("Running for debugging")

    # Set xonsh up and load the xontrib
    setup(xontribs=["bluray"], shell_type="prompt_toolkit")
    _load_xontrib_(XSH)
    # Run the main command loop
    XSH.shell.cmdloop()


if __name__ == "__main__":
    run()
