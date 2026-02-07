# ruff: noqa
"""
I played XONSH but I added CUSTOM TOKENISATION <soyface_thumb.png>
The xonsh tokeniser does not preserve line continuations and indents for lines other than the first when using line continuations.
This is a modified version which does not discard line continuations and which has a modified _tokenize function which preserves indentation for lines other than the first
"""

import io
import itertools
import re
from token import (
    DEDENT,
    ENDMARKER,
    ERRORTOKEN,
    GREATER,
    INDENT,
    LESS,
    NAME,
    NEWLINE,
    NUMBER,
    OP,
    RIGHTSHIFT,
    STRING,
)

from xonsh.lib.lazyasd import lazyobject
from xonsh.parsers.lexer import (
    _make_matcher_handler,
    _new_token,
    handle_double_amps,
    handle_double_pipe,
    handle_error_space,
    handle_error_token,
    handle_ignore,
    handle_name,
    handle_rbrace,
    handle_rbracket,
    handle_redirect,
    handle_rparen,
    token_map,
)
from xonsh.parsers.tokenize import (
    COMMENT,
    DOLLARNAME,
    ENCODING,
    HAS_ASYNC,
    IOREDIRECT1,
    IOREDIRECT2,
    NL,
    SEARCHPATH,
    SearchPath,
    TokenError,
    TokenInfo,
    _compile,
    _redir_check_map,
    _redir_check_single,
    additional_parenlevs,
    detect_encoding,
    endpats,
    getPseudoToken,
    getPseudoTokenWithoutIO,
    single_quoted,
    tabsize,
    triple_quoted,
)

if HAS_ASYNC:
    from xonsh.parsers.tokenize import ASYNC, AWAIT


def custom_get_tokens(
    s, tolerant, pymode=True, tokenize_ioredirects=True, is_subproc=False
):
    """
    Given a string containing xonsh code, generates a stream of relevant PLY
    tokens using ``handle_token``.
    """
    state = {
        "indents": [0],
        "last": None,
        "pymode": [(pymode, "", "", (0, 0))],
        "stream": custom_tokenize(
            io.BytesIO(s.encode("utf-8")).readline,
            tolerant,
            tokenize_ioredirects,
            is_subproc=is_subproc,
        ),
        "tolerant": tolerant,
    }
    while True:
        try:
            token = next(state["stream"])
            yield from custom_handle_token(state, token)
        except StopIteration:
            if len(state["pymode"]) > 1 and not tolerant:
                pm, o, m, p = state["pymode"][-1]
                l, c = p
                e = 'Unmatched "{}" at line {}, column {}'
                yield _new_token("ERRORTOKEN", e.format(o, l, c), (0, 0))
            break
        except TokenError as e:
            # this is recoverable in single-line mode (from the shell)
            # (e.g., EOF while scanning string literal)
            yield _new_token("ERRORTOKEN", e.args[0], (0, 0))
            break
        except IndentationError as e:
            # this is never recoverable
            yield _new_token("ERRORTOKEN", e, (0, 0))
            break


def custom_tokenize(
    readline, tolerant=False, tokenize_ioredirects=True, is_subproc=False
):
    """
    The tokenize() generator requires one argument, readline, which
    must be a callable object which provides the same interface as the
    readline() method of built-in file objects.  Each call to the function
    should return one line of input as bytes.  Alternately, readline
    can be a callable function terminating with StopIteration:
        readline = open(myfile, 'rb').__next__  # Example of alternate readline

    The generator produces 5-tuples with these members: the token type; the
    token string; a 2-tuple (srow, scol) of ints specifying the row and
    column where the token begins in the source; a 2-tuple (erow, ecol) of
    ints specifying the row and column where the token ends in the source;
    and the line on which the token was found.  The line passed is the
    logical line; continuation lines are included.

    The first token sequence will always be an ENCODING token
    which tells you which encoding was used to decode the bytes stream.

    If ``tolerant`` is True, yield ERRORTOKEN with the erroneous string instead of
    throwing an exception when encountering an error.

    If ``tokenize_ioredirects`` is True, produce IOREDIRECT tokens for special
    io-redirection operators like ``2>``. Otherwise, treat code like ``2>`` as
    regular Python code.
    """
    encoding, consumed = detect_encoding(readline)
    rl_gen = iter(readline, b"")
    empty = itertools.repeat(b"")
    return custom__tokenize(
        itertools.chain(consumed, rl_gen, empty).__next__,
        encoding,
        tolerant,
        tokenize_ioredirects,
        is_subproc=is_subproc,
    )


def custom__tokenize(
    readline, encoding, tolerant=False, tokenize_ioredirects=True, is_subproc=False
):
    lnum = parenlev = continued = 0
    numchars = "0123456789"
    contstr, needcont = "", 0
    contline = None
    indents = [0]

    # 'stashed' and 'async_*' are used for async/await parsing
    stashed = None
    async_def = False
    async_def_indent = 0
    async_def_nl = False

    if encoding is not None:
        if encoding == "utf-8-sig":
            # BOM will already have been stripped.
            encoding = "utf-8"
        yield TokenInfo(ENCODING, encoding, (0, 0), (0, 0), "")
    while True:  # loop over lines in stream
        try:
            line = readline()
        except StopIteration:
            line = b""

        is_subproc = is_subproc or line[:2] in {b"![", b"$[", b"$(", b"!("}

        if encoding is not None:
            line = line.decode(encoding)
        lnum += 1
        pos, max = 0, len(line)

        if contstr:  # continued string
            if not line:
                if tolerant:
                    # return the partial string
                    yield TokenInfo(
                        ERRORTOKEN, contstr, strstart, (lnum, end), contline + line
                    )
                    break
                else:
                    raise TokenError("EOF in multi-line string", strstart)
            endmatch = endprog.match(line)
            if endmatch:
                pos = end = endmatch.end(0)
                yield TokenInfo(
                    STRING, contstr + line[:end], strstart, (lnum, end), contline + line
                )
                contstr, needcont = "", 0
                contline = None
            elif needcont and line[-2:] != "\\\n" and line[-3:] != "\\\r\n":
                yield TokenInfo(
                    ERRORTOKEN, contstr + line, strstart, (lnum, len(line)), contline
                )
                contstr = ""
                contline = None
                continue
            else:
                contstr = contstr + line
                contline = contline + line
                continue

        elif parenlev == 0 and not continued:  # new statement
            if not line:
                break
            column = 0
            while pos < max:  # measure leading whitespace
                if line[pos] == " ":
                    column += 1
                elif line[pos] == "\t":
                    column = (column // tabsize + 1) * tabsize
                elif line[pos] == "\f":
                    column = 0
                else:
                    break
                pos += 1
            if pos == max:
                break

            if line[pos] in "#\r\n":  # skip comments or blank lines
                if line[pos] == "#":
                    comment_token = line[pos:].rstrip("\r\n")
                    nl_pos = pos + len(comment_token)
                    yield TokenInfo(
                        COMMENT,
                        comment_token,
                        (lnum, pos),
                        (lnum, pos + len(comment_token)),
                        line,
                    )
                    yield TokenInfo(
                        NL, line[nl_pos:], (lnum, nl_pos), (lnum, len(line)), line
                    )
                else:
                    yield TokenInfo(
                        (NL, COMMENT)[line[pos] == "#"],
                        line[pos:],
                        (lnum, pos),
                        (lnum, len(line)),
                        line,
                    )
                continue

            if column > indents[-1]:  # count indents or dedents
                indents.append(column)
                yield TokenInfo(INDENT, line[:pos], (lnum, 0), (lnum, pos), line)
            while column < indents[-1]:
                if (
                    column not in indents and not tolerant
                ):  # if tolerant, just ignore the error
                    raise IndentationError(
                        "unindent does not match any outer indentation level",
                        ("<tokenize>", lnum, pos, line),
                    )
                indents = indents[:-1]

                if async_def and async_def_indent >= indents[-1]:
                    async_def = False
                    async_def_nl = False
                    async_def_indent = 0

                yield TokenInfo(DEDENT, "", (lnum, pos), (lnum, pos), line)

            if async_def and async_def_nl and async_def_indent >= indents[-1]:
                async_def = False
                async_def_nl = False
                async_def_indent = 0

        else:  # continued statement
            if not line:
                if tolerant:
                    # no need to raise an error, we're done
                    break
                raise TokenError("EOF in multi-line statement", (lnum, 0))
            continued = 0

        while pos < max:
            pseudomatch = _compile(
                getPseudoToken(is_subproc=is_subproc)
                if tokenize_ioredirects
                else getPseudoTokenWithoutIO(is_subproc=is_subproc)
            ).match(line, pos)
            if pseudomatch:  # scan for tokens
                start, end = pseudomatch.span(1)
                spos, epos, pos = (lnum, start), (lnum, end), end
                if start == end:
                    continue
                token, initial = line[start:end], line[start]

                ##### Modified - preserve whitespace after continuations
                pre_start = pseudomatch.span(0)[0]
                pre_token = line[pre_start:start]
                if pre_token.isspace():
                    yield TokenInfo(
                        INDENT, pre_token, (lnum, pre_start), (lnum, start), line
                    )
                ##### End

                if token in _redir_check_single:
                    yield TokenInfo(IOREDIRECT1, token, spos, epos, line)
                elif token in _redir_check_map:
                    yield TokenInfo(IOREDIRECT2, token, spos, epos, line)
                elif initial in numchars or (  # ordinary number
                    initial == "." and token != "." and token != "..."
                ):
                    yield TokenInfo(NUMBER, token, spos, epos, line)
                elif initial in "\r\n":
                    if stashed:
                        yield stashed
                        stashed = None
                    if parenlev > 0:
                        yield TokenInfo(NL, token, spos, epos, line)
                    else:
                        yield TokenInfo(NEWLINE, token, spos, epos, line)
                        if async_def:
                            async_def_nl = True

                elif initial == "#" or (
                    is_subproc and initial == " " and len(token) > 1 and token[1] == "#"
                ):
                    assert not token.endswith("\n")
                    if stashed:
                        yield stashed
                        stashed = None
                    yield TokenInfo(COMMENT, token, spos, epos, line)
                # Xonsh-specific Regex Globbing
                elif re.match(SearchPath, token):
                    yield TokenInfo(SEARCHPATH, token, spos, epos, line)
                elif token in triple_quoted:
                    endprog = _compile(endpats[token])
                    endmatch = endprog.match(line, pos)
                    if endmatch:  # all on one line
                        pos = endmatch.end(0)
                        token = line[start:pos]
                        yield TokenInfo(STRING, token, spos, (lnum, pos), line)
                    else:
                        strstart = (lnum, start)  # multiple lines
                        contstr = line[start:]
                        contline = line
                        break
                elif (
                    initial in single_quoted
                    or token[:2] in single_quoted
                    or token[:3] in single_quoted
                ):
                    if token[-1] == "\n":  # continued string
                        strstart = (lnum, start)
                        endprog = _compile(
                            endpats[initial] or endpats[token[1]] or endpats[token[2]]
                        )
                        contstr, needcont = line[start:], 1
                        contline = line
                        break
                    else:  # ordinary string
                        yield TokenInfo(STRING, token, spos, epos, line)
                elif token.startswith("$") and (
                    token[1:].isidentifier() or token[1:2].isalnum()
                ):
                    yield TokenInfo(DOLLARNAME, token, spos, epos, line)
                elif initial.isidentifier():  # ordinary name
                    if token in ("async", "await"):
                        if async_def:
                            yield TokenInfo(
                                ASYNC if token == "async" else AWAIT,
                                token,
                                spos,
                                epos,
                                line,
                            )
                            continue

                    tok = TokenInfo(NAME, token, spos, epos, line)
                    if token == "async" and not stashed:
                        stashed = tok
                        continue

                    if (
                        HAS_ASYNC
                        and token == "def"
                        and (
                            stashed
                            and stashed.type == NAME
                            and stashed.string == "async"
                        )
                    ):
                        async_def = True
                        async_def_indent = indents[-1]

                        yield TokenInfo(
                            ASYNC,
                            stashed.string,
                            stashed.start,
                            stashed.end,
                            stashed.line,
                        )
                        stashed = None

                    if stashed:
                        yield stashed
                        stashed = None

                    yield tok
                elif token == "\\\n" or token == "\\\r\n":  # continued stmt
                    continued = 1
                    yield TokenInfo(ERRORTOKEN, token, spos, epos, line)
                elif initial == "\\":  # continued stmt
                    # for cases like C:\\path\\to\\file
                    continued = 1
                else:
                    if initial in "([{":
                        parenlev += 1
                    elif initial in ")]}":
                        parenlev -= 1
                    elif token in additional_parenlevs:
                        parenlev += 1
                    if stashed:
                        yield stashed
                        stashed = None
                    yield TokenInfo(OP, token, spos, epos, line)
            else:
                yield TokenInfo(
                    ERRORTOKEN, line[pos], (lnum, pos), (lnum, pos + 1), line
                )
                pos += 1

    if stashed:
        yield stashed
        stashed = None

    for _ in indents[1:]:  # pop remaining indent levels
        yield TokenInfo(DEDENT, "", (lnum, 0), (lnum, 0), "")
    yield TokenInfo(ENDMARKER, "", (lnum, 0), (lnum, 0), "")


@lazyobject
def custom_special_handlers():
    """Mapping from ``tokenize`` tokens (or token types) to the proper
    function for generating PLY tokens from them.  In addition to
    yielding PLY tokens, these functions may manipulate the Lexer's state.
    """
    sh = {
        NL: handle_ignore,
        COMMENT: handle_ignore,
        ENCODING: handle_ignore,
        ENDMARKER: handle_ignore,
        NAME: handle_name,
        ERRORTOKEN: handle_error_token,
        LESS: handle_redirect,
        GREATER: handle_redirect,
        RIGHTSHIFT: handle_redirect,
        IOREDIRECT1: handle_redirect,
        IOREDIRECT2: handle_redirect,
        (OP, "<"): handle_redirect,
        (OP, ">"): handle_redirect,
        (OP, ">>"): handle_redirect,
        (OP, ")"): handle_rparen,
        (OP, "}"): handle_rbrace,
        (OP, "]"): handle_rbracket,
        (OP, "&&"): handle_double_amps,
        (OP, "||"): handle_double_pipe,
        (ERRORTOKEN, " "): handle_error_space,
        (ERRORTOKEN, "\\\n"): custom_handle_error_linecont,
        (ERRORTOKEN, "\\\r\n"): custom_handle_error_linecont,
    }
    _make_matcher_handler("(", "LPAREN", True, ")", sh)
    _make_matcher_handler("[", "LBRACKET", True, "]", sh)
    _make_matcher_handler("{", "LBRACE", True, "}", sh)
    _make_matcher_handler("$(", "DOLLAR_LPAREN", False, ")", sh)
    _make_matcher_handler("$[", "DOLLAR_LBRACKET", False, "]", sh)
    _make_matcher_handler("${", "DOLLAR_LBRACE", True, "}", sh)
    _make_matcher_handler("!(", "BANG_LPAREN", False, ")", sh)
    _make_matcher_handler("![", "BANG_LBRACKET", False, "]", sh)
    _make_matcher_handler("@(", "AT_LPAREN", True, ")", sh)
    _make_matcher_handler("@$(", "ATDOLLAR_LPAREN", False, ")", sh)
    return sh


def custom_handle_error_linecont(state, token: TokenInfo):
    yield _new_token("WS", token.string, token.start)


def custom_handle_token(state, token):
    """
    General-purpose token handler.  Makes use of ``token_map`` or
    ``special_map`` to yield one or more PLY tokens from the given input.

    Parameters
    ----------
    state
        The current state of the lexer, including information about whether
        we are in Python mode or subprocess mode, which changes the lexer's
        behavior.  Also includes the stream of tokens yet to be considered.
    token
        The token (from ``tokenize``) currently under consideration
    """
    typ = token.type
    st = token.string
    pymode = state["pymode"][-1][0]
    if not pymode:
        if state["last"] is not None and state["last"].end != token.start:
            cur = token.start
            old = state["last"].end
            if cur[0] == old[0] and cur[1] > old[1]:
                yield _new_token("WS", token.line[old[1] : cur[1]], old)
    if (typ, st) in custom_special_handlers:
        yield from custom_special_handlers[(typ, st)](state, token)
    elif (typ, st) in token_map:
        state["last"] = token
        yield _new_token(token_map[(typ, st)], st, token.start)
    elif typ in custom_special_handlers:
        yield from custom_special_handlers[typ](state, token)
    elif typ in token_map:
        state["last"] = token
        yield _new_token(token_map[typ], st, token.start)
    else:
        m = f"Unexpected token: {token}"
        yield _new_token("ERRORTOKEN", m, token.start)
