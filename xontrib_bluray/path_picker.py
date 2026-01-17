from asyncio import Future
from collections.abc import Iterable
from configparser import ConfigParser
from pathlib import Path
from typing import override

from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import FormattedTextControl, HSplit, Window, WindowAlign
from prompt_toolkit.widgets import Dialog, Label

from xontrib_bluray.constants import MAX_CONTENT_HEIGHT, STATE_FILE


def is_dotfile(path: Path) -> bool:
    return path.name.startswith(".")


# Shitty settings management, can't really justify adding a package for this when it's literally just 1 setting
def read_show_dotfiles_state() -> bool:
    if not STATE_FILE.exists():
        return True

    state = ConfigParser()
    state.read(STATE_FILE)
    if state.has_section("state"):
        return state["state"].getboolean("show_dotfiles", True)
    else:
        return True


def write_show_dotfiles_state(show: bool):
    state = ConfigParser()
    state["state"] = {"show_dotfiles": show}
    with open(STATE_FILE, "w") as file:
        state.write(file)


class PathPicker:
    def __init__(
        self, current_dir: Path | None = None, selected_item: Path | None = None
    ):
        self.show_dotfiles = read_show_dotfiles_state()

        self.kb = KeyBindings()
        self.bottom_bar = Label("", style="grey italic", align=WindowAlign.RIGHT)
        self.current_dir = current_dir or Path(".").absolute()
        self.future = Future[Path | None]()
        self.options: list[Path]
        self._update_options_list(self.current_dir)
        self.selected_option = (
            0 if selected_item is None else self.options.index(selected_item)
        )
        self.list_offset = 0
        self.old_selected_options: dict[Path, int] = {}

        kb = self.kb

        @kb.add("up")
        def _(event):
            self._move_cursor(-1)

        @kb.add("down")
        def _(event):
            self._move_cursor(1)

        @kb.add("left")
        def _(event):
            self._navigate_up()

        @kb.add("right")
        def _(event):
            self._navigate_down()

        @kb.add("enter")
        def _(event):
            self._selected()

        @kb.add(
            Keys.Escape, eager=True
        )  # Not sure why, but esc specifically has a weird delay for closing it
        @kb.add(Keys.Backspace)
        @kb.add("q")
        @kb.add("c-q")
        @kb.add("c-c")
        def _(event):
            self._cancelled()

        @kb.add(".")
        def _(event):
            self._toggle_dotfiles()

        @kb.add("end")
        def _(event):
            if not self.options:
                return

            self.selected_option = len(self.options) - 1
            self.list_offset = len(self.options) - MAX_CONTENT_HEIGHT

        @kb.add("home")
        def _(event):
            self.selected_option = 0
            self.list_offset = 0

        @kb.add("~")
        def _(event):
            self._navigate_home()

        self.container = HSplit(
            [
                Window(
                    FormattedTextControl(self._draw, focusable=True, key_bindings=kb),
                    always_hide_cursor=True,
                ),
                self.bottom_bar,
            ]
        )

        self._update_bottom_bar()

    def _move_cursor(self, direction: int) -> None:
        # Prevent modulo by 0 errors
        if not self.options:
            return

        self.selected_option = (self.selected_option + direction) % len(self.options)
        self._update_list_offset()

    def _navigate_home(self):
        new_dir = Path.home()

        try:
            self._update_options_list(new_dir)
        except OSError:
            return

        self.old_selected_options[self.current_dir] = self.selected_option
        index_of_current_item_in_parent = (
            self.options.index(self.current_dir)
            if self.current_dir in self.options
            else 0
        )
        self.selected_option = self.old_selected_options.get(
            new_dir, index_of_current_item_in_parent
        )
        self.current_dir = new_dir
        self._update_list_offset()

    def _navigate_up(self):
        new_dir = self.current_dir.parent

        try:
            self._update_options_list(new_dir)
        except OSError:
            return

        index_of_current_item_in_parent = (
            self.options.index(self.current_dir)
            # Toggling dotfiles may cause the current directory to disappear
            if self.current_dir in self.options
            else 0
        )

        self.old_selected_options[self.current_dir] = self.selected_option
        self.selected_option = index_of_current_item_in_parent
        self.current_dir = new_dir
        self._update_list_offset()

    def _navigate_down(self):
        if not self.options:
            return

        new_dir = self.options[self.selected_option]

        if not new_dir.is_dir():
            return

        try:
            self._update_options_list(new_dir)
        except OSError:
            return

        self.old_selected_options[self.current_dir] = self.selected_option
        self.current_dir = new_dir
        self.selected_option = self.old_selected_options.get(self.current_dir, 0)
        self._update_list_offset()

    def _toggle_dotfiles(self):
        old_options = self.options
        old_selection = self.selected_option
        selection = self.options[self.selected_option]
        self.show_dotfiles = not self.show_dotfiles
        self._update_options_list(self.current_dir)
        self._update_bottom_bar()
        write_show_dotfiles_state(self.show_dotfiles)

        if selection in self.options:
            # If the selected is still in the list, re-select it
            self.selected_option = self.options.index(selection)
        else:
            # If the old selection is no longer in the options list, try to select the closest thing to it that is still in the list

            def find_nearest_item(items: Iterable[Path]) -> tuple[int, Path | None]:
                for distance, option in enumerate(items):
                    if option in self.options:
                        return distance, option

                return 0, None

            max_items_to_check = 20

            # Search forwards in the list
            forwards_distance, forwards_item = find_nearest_item(
                old_options[old_selection + 1 : old_selection + max_items_to_check :]
            )
            # Search backwards in the list
            backwards_distance, backwards_item = find_nearest_item(
                old_options[old_selection - 1 : old_selection - max_items_to_check : -1]
            )

            # Select the nearest previous or next item
            if forwards_item and backwards_item:
                if backwards_distance < forwards_distance:
                    self.selected_option = self.options.index(backwards_item)
                else:
                    self.selected_option = self.options.index(forwards_item)
            elif forwards_item:
                self.selected_option = self.options.index(forwards_item)
            elif backwards_item:
                self.selected_option = self.options.index(backwards_item)
            else:
                # Fallback
                self.selected_option = 0

        self._update_list_offset()

    def _update_list_offset(self):
        if self.selected_option >= self.list_offset + MAX_CONTENT_HEIGHT - 1:
            self.list_offset = self.selected_option - MAX_CONTENT_HEIGHT + 1
        elif self.selected_option < self.list_offset:
            self.list_offset = self.selected_option

    def _update_bottom_bar(self):
        dotfile_icon = "\uf441" if self.show_dotfiles else "\uf4c5"

        self.bottom_bar.text = f"{dotfile_icon} Dotfiles"

    def _update_options_list(self, new_dir: Path):
        def dotfiles_filter(path: Path):
            if self.show_dotfiles:
                return True
            else:
                return not is_dotfile(path)

        items = list(filter(dotfiles_filter, new_dir.iterdir()))

        def name_key(it: Path):
            return it.name.lower()

        dirs = sorted(filter(lambda it: it.is_dir(), items), key=name_key)
        files = sorted(filter(lambda it: it.is_file(), items), key=name_key)

        self.options = list(dirs + files)
        # Add an option to select the current directory, always at the top of the list
        self.options.insert(0, new_dir)

    def _selected(self):
        # TODO: need a way to only allow directories or files to be selected
        self.future.set_result(self.options[self.selected_option])

    def _cancelled(self):
        self.future.set_result(None)

    def _draw(self) -> StyleAndTextTuples:
        if not self.options:
            return [("#ff0000", "It's empty here!")]

        tokens = []
        this_dir_label = "<this directory>"
        # Only render the options which are visible, much more efficient for directories with tons of items in them
        visible_options = self.options[
            self.list_offset : self.list_offset + MAX_CONTENT_HEIGHT
        ]
        longest_name = max(
            max(len(option.name) for option in visible_options), len(this_dir_label)
        )

        for visible_idx, option in enumerate(visible_options):
            idx = visible_idx + self.list_offset
            if idx == self.selected_option:
                tokens.append(("[SetCursorPosition]", ""))

            is_selected = idx == self.selected_option

            icon = "\uf114" if option.is_dir() else "\uf016"
            hidden_class = (
                "class:list.dir.hidden" if option.is_dir() else "class:list.file.hidden"
            )
            normal_class = "class:list.dir" if option.is_dir() else "class:list.file"
            type_class = hidden_class if is_dotfile(option) else normal_class
            prefix = ">" if is_selected else " "

            # special handling for selecting this directory
            if option == self.current_dir:
                combined_class = (
                    "class:list.selected" if is_selected else "class:list.thisdir"
                )
                tokens.append((combined_class, f"{prefix} "))
                tokens.append(
                    (
                        f"{combined_class} italic",
                        this_dir_label
                        + (" " * (longest_name - len(this_dir_label) + 2)),
                    )
                )
            else:
                combined_class = "class:list.selected" if is_selected else type_class
                tokens.append(
                    (
                        combined_class,
                        f"{prefix} {icon} {option.name}"
                        + " " * (longest_name - len(option.name)),
                    )
                )

            tokens.append(("", "\n"))

        # remove the trailing \n
        tokens.pop()

        return tokens

    def __pt_container__(self):
        return self.container


class PathPickerDialog(PathPicker):
    def __init__(
        self, current_dir: Path | None = None, selected_item: Path | None = None
    ):
        super().__init__(current_dir=current_dir, selected_item=selected_item)
        self.dialog = Dialog(
            self.container,
            title=str(self.current_dir),
            modal=True,
        )

    @override
    def _navigate_down(self):
        super()._navigate_down()
        self.dialog.title = str(self.current_dir)

    @override
    def _navigate_up(self):
        super()._navigate_up()
        self.dialog.title = str(self.current_dir)

    @override
    def _navigate_home(self):
        super()._navigate_home()
        self.dialog.title = str(self.current_dir)

    @override
    def __pt_container__(self):
        return self.dialog
