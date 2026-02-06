from prompt_toolkit.application import get_app
from prompt_toolkit.auto_suggest import AutoSuggest
from prompt_toolkit.buffer import BufferAcceptHandler
from prompt_toolkit.completion import Completer
from prompt_toolkit.filters import FilterOrBool
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.history import History
from prompt_toolkit.layout import AnyDimension
from prompt_toolkit.layout.controls import GetLinePrefixCallable
from prompt_toolkit.layout.processors import Processor
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.validation import Validator
from prompt_toolkit.widgets import SearchToolbar, TextArea


class FocusStyleableTextArea(TextArea):
    def __init__(
        self,
        text: str = "",
        multiline: FilterOrBool = True,
        password: FilterOrBool = False,
        lexer: Lexer | None = None,
        auto_suggest: AutoSuggest | None = None,
        completer: Completer | None = None,
        complete_while_typing: FilterOrBool = True,
        validator: Validator | None = None,
        accept_handler: BufferAcceptHandler | None = None,
        history: History | None = None,
        focusable: FilterOrBool = True,
        focus_on_click: FilterOrBool = False,
        wrap_lines: FilterOrBool = True,
        read_only: FilterOrBool = False,
        width: AnyDimension = None,
        height: AnyDimension = None,
        dont_extend_height: FilterOrBool = False,
        dont_extend_width: FilterOrBool = False,
        line_numbers: bool = False,
        get_line_prefix: GetLinePrefixCallable | None = None,
        scrollbar: bool = False,
        style: str = "",
        search_field: SearchToolbar | None = None,
        preview_search: FilterOrBool = True,
        prompt: AnyFormattedText = "",
        input_processors: list[Processor] | None = None,
        name: str = "",
    ):
        super().__init__(
            text,
            multiline,
            password,
            lexer,
            auto_suggest,
            completer,
            complete_while_typing,
            validator,
            accept_handler,
            history,
            focusable,
            focus_on_click,
            wrap_lines,
            read_only,
            width,
            height,
            dont_extend_height,
            dont_extend_width,
            line_numbers,
            get_line_prefix,
            scrollbar,
            style,
            search_field,
            preview_search,
            prompt,
            input_processors,
            name,
        )
        self._original_style = style
        self.window.style = self.get_style

    def get_style(self) -> str:
        if get_app().layout.has_focus(self):
            return "class:text-area.focused " + self._original_style
        else:
            return "class:text-area " + self._original_style
