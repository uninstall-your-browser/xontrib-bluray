from xonsh.parsers.lexer import Lexer

from xontrib_bluray.custom_tokenisation import custom_get_tokens


class CustomLexer(Lexer):
    """
    This lexer preserves whitespace
    """

    def input(self, s, is_subproc=False):
        """Calls the lexer on the string s."""
        self._token_stream = custom_get_tokens(
            s, self._tolerant, self._pymode, is_subproc=is_subproc
        )

    def split(self, s):
        """A modified version of the split function which preserves whitespace from the input string"""
        self.input(s, is_subproc=True)
        elements = []
        l = c = -1
        nl = "\n"
        last_was_whitespace = False

        for token in self:
            if token.type in ["WS", "INDENT"]:
                elements.append(token.value)
                last_was_whitespace = True
            elif l < token.lineno:
                if token.value != "":
                    elements.append(token.value)
                last_was_whitespace = False
            elif len(elements) > 0 and c == token.lexpos:
                if last_was_whitespace:
                    elements.append(token.value)
                else:
                    elements[-1] = elements[-1] + token.value

                last_was_whitespace = False
            else:
                elements.append(token.value)
                last_was_whitespace = False

            nnl = token.value.count(nl)
            if nnl == 0:
                l = token.lineno
                c = token.lexpos + len(token.value)
            else:
                l = token.lineno + nnl
                c = len(token.value.rpartition(nl)[-1])

        return elements
