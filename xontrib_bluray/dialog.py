from asyncio import Future
from collections.abc import Callable
from typing import Protocol

from prompt_toolkit.application import get_app
from prompt_toolkit.layout import Float, FloatContainer
from prompt_toolkit.layout.layout import FocusableElement


class DialogFuture[T](Protocol):
    future: Future[T]


async def show_as_float[T](
    dialog: DialogFuture[T] | FocusableElement,
    height: int | Callable[[], int] = None,
    width: int | Callable[[], int] = None,
    top: int | None = None,
    right: int | None = None,
    bottom: int | None = None,
    left: int | None = None,
) -> T:
    # In order to use a floating dialog, we need to have something to add it to. Since xonsh (PTK shell) works by
    # forever calling `.prompt` from its internals (see `xonsh.shells.ptk_shell.PromptToolkitShell#singleline`), it
    # always has a PTK application 'running', even if it is just asking for a line of text. This means that we can't
    # just use PTK shortcuts or create our own application, because one is already running and it won't work.
    # Instead, we can go through the elements of the internal root layout inside the PromptSession which conveniently
    # uses a FloatContainer (intended to be used for completions and rprompt), which is just what we need for our
    # floating dialog. It may be worth xonsh implementing its own application instead of using PromptSession, which
    # would allow all kinds of fancy UI components to be added to the shell.
    app = get_app()
    root_container: FloatContainer = app.layout.container.children[
        0
    ].alternative_content

    float_ = Float(
        content=dialog,
        height=height,
        width=width,
        top=top,
        left=left,
        right=right,
        bottom=bottom,
    )
    root_container.floats.insert(0, float_)

    focused_before = app.layout.current_window
    app.layout.focus(dialog)
    result = await dialog.future
    app.layout.focus(focused_before)

    if float_ in root_container.floats:
        root_container.floats.remove(float_)

    return result
