from xonsh.built_ins import XonshSession


def _load_xontrib_(xsh: XonshSession, **_):
    import os
    import re
    from asyncio import ensure_future
    from pathlib import Path
    from typing import NamedTuple

    from prompt_toolkit.application import get_app
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
    from prompt_toolkit.keys import Keys
    from prompt_toolkit.styles import merge_styles
    from xonsh.events import events
    from xonsh.prompt.base import PromptFields
    from xonsh.shells.ptk_shell import PromptToolkitShell

    from xontrib_bluray import constants, dialog
    from xontrib_bluray.constants import STATE_FILE
    from xontrib_bluray.custom_lexer import CustomLexer
    from xontrib_bluray.path_picker import PathPickerDialog

    STATE_FILE.parent.mkdir(exist_ok=True, parents=True)

    path_string_pattern = re.compile("^[pf]?['\"]?(.+?)[\"']?$")

    def split_prompt_to_args(prompt: str) -> list[str]:
        split_prompt = CustomLexer(tolerant=False, pymode=False).split(prompt)
        result = []

        for split in split_prompt:
            result.append(split)

        return result

    class SelectedArg(NamedTuple):
        position: int
        is_inserting: bool

    def get_selected_prompt_arg(
        prompt_args: list[str], cursor_position: int
    ) -> SelectedArg:
        arg_position: int = -1
        is_inserting = True
        current_arg_start_position = 0

        for idx, arg in enumerate(prompt_args):
            if cursor_position > current_arg_start_position or (
                arg.isspace() and cursor_position == current_arg_start_position
            ):
                arg_position = idx
                is_inserting = arg.isspace()
            elif cursor_position <= current_arg_start_position:
                break

            current_arg_start_position += len(arg)
        else:
            if cursor_position >= current_arg_start_position:
                arg_position = len(prompt_args)
                # If it is, we will be inserting
                is_inserting = True

        return SelectedArg(is_inserting=is_inserting, position=arg_position)

    class PutResult(NamedTuple):
        new_prompt: str
        new_cursor_position: int

    def put_arg_in_prompt(
        *,
        prompt_args: list[str],
        selected_arg: SelectedArg,
        new_arg: str,
        cursor_position: int,
    ) -> PutResult:
        arg_position = selected_arg.position
        is_inserting = selected_arg.is_inserting

        if len(prompt_args) == 0:
            # Must not use .insert if the array is empty
            prompt_args.append(new_arg)
        elif arg_position == -1:
            prompt_args.insert(0, new_arg + " ")
        elif arg_position == len(prompt_args):
            prompt_args.append(" " + new_arg)
        elif is_inserting:
            insertion_position = cursor_position - sum(
                len(arg) for arg in prompt_args[:arg_position]
            )

            arg_text = prompt_args[arg_position]
            text_before = arg_text[:insertion_position]
            text_after = arg_text[insertion_position:]
            prompt_args[arg_position] = new_arg

            # Ensure that the new arg is followed by a space
            if arg_position < len(prompt_args):
                if len(text_after) > 0:
                    prompt_args.insert(arg_position + 1, text_after)
                # len check is for short-circuiting and preventing out of bounds error!
                elif len(text_after) == 0 or not text_after[0].isspace():
                    prompt_args[arg_position + 1] = " " + prompt_args[arg_position + 1]

            # Ensure that the new arg is preceded by a space
            if arg_position > 0:
                if len(text_before) > 0:
                    prompt_args.insert(arg_position, text_before)
                    arg_position += 1
                # len check is for short-circuiting and preventing out of bounds error!
                elif len(text_before) == 0 or not text_before[-1].isspace():
                    prompt_args.insert(arg_position, " ")
                    arg_position += 1
        else:
            prompt_args[arg_position] = new_arg

        return PutResult(
            new_cursor_position=sum(
                len(arg) for arg in prompt_args[: arg_position + 1]
            ),
            new_prompt="".join(prompt_args),
        )

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
        def show_interactive_cd(event: KeyPressEvent):
            ensure_added_styles()

            async def coro():
                nonlocal event, _is_open

                if not _is_open:
                    _is_open = True
                    try:
                        new_dir: Path | None = await dialog.show_as_float(
                            PathPickerDialog("Change directory", accept_files=False),
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

        @bindings.add(Keys.ControlY, filter=is_not_open)
        def show_interactive_path_picker(event: KeyPressEvent):
            ensure_added_styles()

            def create_path_picker_dialog(
                prompt_args: list[str], selected_arg: SelectedArg
            ) -> PathPickerDialog:
                current_dir = None
                selected_file = None

                if not selected_arg.is_inserting:
                    title = "Choose a path to replace this path which is somehow invalid? Wtf are you doing man"

                    selected_path_match = path_string_pattern.match(
                        prompt_args[selected_arg.position]
                    )
                    if selected_path_match:
                        try:
                            selected_path = Path(
                                selected_path_match.group(1)
                            ).absolute()
                        except ValueError:
                            pass
                        else:
                            if selected_path.exists():
                                selected_file = selected_path

                            if selected_path.parent.exists():
                                current_dir = selected_path.parent

                            # TODO make this shorten the path if it's too long instead of just using the file name
                            title = f"Replace {selected_path.name}"
                else:
                    title = "Insert a path"

                return PathPickerDialog(
                    current_dir=current_dir, selected_item=selected_file, title=title
                )

            async def coro():
                nonlocal event, _is_open

                if not _is_open:
                    _is_open = True
                    try:
                        prompt_text = event.current_buffer.text
                        cursor_position = event.current_buffer.cursor_position
                        prompt_args = split_prompt_to_args(prompt_text)
                        selected_arg = get_selected_prompt_arg(
                            prompt_args, cursor_position
                        )

                        new_dir: Path | None = await dialog.show_as_float(
                            create_path_picker_dialog(prompt_args, selected_arg),
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

                        put_result = put_arg_in_prompt(
                            selected_arg=selected_arg,
                            prompt_args=prompt_args,
                            new_arg=path_text,
                            cursor_position=cursor_position,
                        )
                        event.current_buffer.text = put_result.new_prompt
                        event.current_buffer.cursor_position = (
                            put_result.new_cursor_position
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
