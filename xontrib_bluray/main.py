from dataclasses import dataclass

from prompt_toolkit.key_binding import KeyBindings
from xonsh.built_ins import XonshSession

from xontrib_bluray.custom_lexer import CustomLexer


def _load_xontrib_(xsh: XonshSession, **_):
    import os
    from asyncio import ensure_future
    from pathlib import Path

    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyPressEvent
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.styles import merge_styles
    from xonsh.events import events
    from xonsh.prompt.base import PromptFields
    from xonsh.shells.ptk_shell import PromptToolkitShell

    from xontrib_bluray import constants, dialog
    from xontrib_bluray.constants import STATE_FILE
    from xontrib_bluray.path_picker import PathPickerDialog

    STATE_FILE.parent.mkdir(exist_ok=True, parents=True)

    @dataclass
    class PromptArg:
        position: int
        text: str

    def split_prompt_to_args(prompt: str) -> list[PromptArg]:
        split_prompt = CustomLexer(tolerant=False, pymode=False).split(prompt)
        cumulative_length = 0
        result = []

        for split in split_prompt:
            result.append(PromptArg(position=cumulative_length, text=split))
            cumulative_length += len(split)

        return result

    @events.on_ptk_create
    def custom_keybindings(bindings: KeyBindings, **kw):
        added_styles = False
        _is_open = False

        def ensure_added_styles():
            nonlocal added_styles
            if not added_styles:
                get_app().style = merge_styles([get_app().style, constants.style])
                added_styles = True

        @Condition
        def is_not_open():
            return not _is_open

        @bindings.add(Keys.ControlK, filter=is_not_open)
        @bindings.add(Keys.ControlY, filter=is_not_open)  # Mainly for pycharm
        def show_interactive_cd(event: KeyPressEvent):
            ensure_added_styles()

            async def coro():
                nonlocal event, _is_open

                if not _is_open:
                    _is_open = True
                    try:
                        new_dir: Path | None = await dialog.show_as_float(
                            PathPickerDialog(),
                            height=20,
                            bottom=0,
                            top=1,
                            left=0,
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
                        _is_open = False

            ensure_future(coro())

        @bindings.add(Keys.ControlJ, filter=is_not_open)
        def show_interactive_path_picker(event: KeyPressEvent):
            ensure_added_styles()

            async def coro():
                nonlocal event, _is_open

                if not _is_open:
                    _is_open = True
                    try:
                        new_dir: Path | None = await dialog.show_as_float(
                            PathPickerDialog(),
                            height=20,
                            bottom=0,
                            top=1,
                            left=0,
                        )

                        if not new_dir:
                            return

                        # TODO use ../ instead of absolute path, with a limit of ../../../

                        current_dir = Path(".").absolute()

                        if new_dir.is_relative_to(current_dir):
                            new_dir = new_dir.relative_to(current_dir)

                        path_text = f'p"{str(new_dir).replace("\\", "\\\\").replace('"', '\\"')}"'
                        prompt_text = event.current_buffer.text
                        cursor_position = event.current_buffer.cursor_position

                        if cursor_position == 0:
                            event.current_buffer.insert_text(f"{path_text} ")
                            return
                        elif cursor_position == len(event.current_buffer.text):
                            event.current_buffer.insert_text(f" {path_text}")
                            return

                        prompt_args = split_prompt_to_args(prompt_text)
                        selected_arg: int | None = None

                        for idx, arg in enumerate(prompt_args):
                            if cursor_position >= arg.position:
                                selected_arg = idx

                        assert selected_arg is not None

                        if prompt_args[selected_arg].text.isspace():
                            if (
                                cursor_position >= 1
                                and not prompt_text[cursor_position - 1].isspace()
                            ):
                                event.current_buffer.insert_text(f" {path_text}")
                            else:
                                event.current_buffer.insert_text(path_text)
                        elif (
                            cursor_position >= 1
                            and prompt_text[cursor_position - 1 : cursor_position + 1]
                            == " -"
                        ):
                            """
                            for the case of inserting when the cursor is positioned like this
                            somecommand --arg
                                        ^ cursor is here
                            This would normally replace --arg, but I found this to be really confusing during testing,
                            and I think inserting infront of --arg is more intuitive
                            """
                            event.current_buffer.insert_text(f"{path_text} ")
                        else:
                            prev_len = len(prompt_text)
                            prompt_args[selected_arg].text = path_text
                            event.current_buffer.text = "".join(
                                arg.text for arg in prompt_args
                            )
                            # Move the cursor back
                            event.current_buffer.cursor_position -= prev_len - len(
                                event.current_buffer.text
                            )
                    finally:
                        _is_open = False

            ensure_future(coro())


def run():
    """
    Start a xonsh shell from python for pycharm debugging
    """
    import os

    from xonsh.built_ins import XSH
    from xonsh.main import setup

    print("Running for debugging")

    # prevent writing history to disk
    os.environ["XONSH_HISTORY_BACKEND"] = "dummy"
    # Set xonsh up and load the xontrib
    setup(shell_type="prompt_toolkit")
    _load_xontrib_(XSH)
    # Run the main command loop
    XSH.shell.cmdloop()


if __name__ == "__main__":
    run()
