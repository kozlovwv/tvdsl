# Token spec of the Funny language.
#   NAME [skip] = regex
# Order is priority on equal-length matches: keywords must precede IDENT.
# Alphabet is ASCII; any other character leads to the trap.

# Keywords. `function` and `length` are reserved as the HW1 statement requires,
# though in the Funny grammar there is no `function` and `length` is a builtin function.
KW_FUNCTION  = function
KW_REQUIRES  = requires
KW_RETURNS   = returns
KW_ENSURES   = ensures
KW_USES      = uses
KW_INT       = int
KW_IF        = if
KW_ELSE      = else
KW_WHILE     = while
KW_INVARIANT = invariant
KW_ASSERT    = assert
KW_ASSUME    = assume
KW_TRUE      = true
KW_FALSE     = false
KW_NOT       = not
KW_AND       = and
KW_OR        = or
KW_FORALL    = forall
KW_EXISTS    = exists
KW_LENGTH    = length

IDENT        = [A-Za-z_][A-Za-z0-9_]*
INT          = 0|[1-9][0-9]*

# Multi-char operators; longest match picks them over their one-char prefixes.
ARROW        = ->
IMPLIES      = =>
EQ           = ==
NE           = !=
LE           = <=
GE           = >=
LT           = <
GT           = >
ASSIGN       = =
PLUS         = \+
MINUS        = -
STAR         = \*
SLASH        = /
COMMA        = ,
SEMI         = ;
COLON        = :
PIPE         = \|
LPAREN       = \(
RPAREN       = \)
LBRACKET     = \[
RBRACKET     = \]
LBRACE       = {
RBRACE       = }

WS      skip = [ \t\r\n]+
COMMENT skip = //[^\n]*
