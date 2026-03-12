"""
Detection normalizer: parse condition string with tokenizer + recursive descent,
resolve selection references, reject unsupported features. Output for ast_builder.
"""

from sigma_similarity.errors import UnsupportedSigmaFeatureError

# -----------------------------------------------------------------------------
# Tokenizer: explicit token types, no regex-based grammar shortcuts
# -----------------------------------------------------------------------------

from enum import Enum
from typing import Any


class TokenType(Enum):
    IDENT = "ident"
    AND = "and"
    OR = "or"
    NOT = "not"
    ONE = "one"      # "1" in "1 of"
    ALL = "all"      # "all" in "all of"
    OF = "of"
    LPAREN = "lparen"
    RPAREN = "rparen"
    EOF = "eof"


class Token:
    __slots__ = ("type", "value", "start")

    def __init__(self, type: TokenType, value: str = "", start: int = 0):
        self.type = type
        self.value = value
        self.start = start

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r})"


def _tokenize_condition(condition: str) -> list[Token]:
    """Tokenize condition string. Explicit scan; no regex for grammar."""
    if not isinstance(condition, str):
        raise UnsupportedSigmaFeatureError("condition must be a string")
    condition = condition.strip()
    tokens: list[Token] = []
    i = 0
    n = len(condition)
    while i < n:
        while i < n and condition[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        c = condition[i]
        if c == "(":
            tokens.append(Token(TokenType.LPAREN, "(", start))
            i += 1
            continue
        if c == ")":
            tokens.append(Token(TokenType.RPAREN, ")", start))
            i += 1
            continue
        if c.isalnum() or c == "_" or c == "*":
            j = i
            while j < n and (condition[j].isalnum() or condition[j] in "_*"):
                j += 1
            word = condition[i:j]
            low = word.lower()
            if low == "and":
                tokens.append(Token(TokenType.AND, word, start))
            elif low == "or":
                tokens.append(Token(TokenType.OR, word, start))
            elif low == "not":
                tokens.append(Token(TokenType.NOT, word, start))
            elif low == "all":
                tokens.append(Token(TokenType.ALL, word, start))
            elif low == "of":
                tokens.append(Token(TokenType.OF, word, start))
            elif word == "1":
                tokens.append(Token(TokenType.ONE, word, start))
            else:
                tokens.append(Token(TokenType.IDENT, word, start))
            i = j
            continue
        i += 1
    tokens.append(Token(TokenType.EOF, "", n))
    return tokens


# -----------------------------------------------------------------------------
# Reject unsupported: count, near, temporal, etc.
# -----------------------------------------------------------------------------


def _reject_unsupported_condition(condition: str) -> None:
    """Raise UnsupportedSigmaFeatureError if condition uses unsupported features."""
    lower = condition.lower()
    if "count(" in lower or "count (" in lower:
        raise UnsupportedSigmaFeatureError("count() is not supported")
    if " near " in lower or " near(" in lower or "(near " in lower:
        raise UnsupportedSigmaFeatureError("near is not supported")
    if "temporal" in lower or "sequence" in lower or "aggregation" in lower:
        raise UnsupportedSigmaFeatureError("temporal/sequence/aggregation not supported")
    if " correlation " in lower:
        raise UnsupportedSigmaFeatureError("correlation rules not supported")


# -----------------------------------------------------------------------------
# Recursive descent parser
# -----------------------------------------------------------------------------


class ConditionNode:
    """Base for parsed condition tree (before selection resolution)."""
    pass


class AndNode(ConditionNode):
    __slots__ = ("children",)

    def __init__(self, children: list[ConditionNode]):
        self.children = children


class OrNode(ConditionNode):
    __slots__ = ("children",)

    def __init__(self, children: list[ConditionNode]):
        self.children = children


class NotNode(ConditionNode):
    __slots__ = ("child",)

    def __init__(self, child: ConditionNode):
        self.child = child


class OneOfNode(ConditionNode):
    __slots__ = ("ident",)

    def __init__(self, ident: str):
        self.ident = ident


class AllOfNode(ConditionNode):
    __slots__ = ("ident",)

    def __init__(self, ident: str):
        self.ident = ident


class IdentNode(ConditionNode):
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _current(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def _advance(self) -> Token:
        t = self._current()
        if self.pos < len(self.tokens) and self.tokens[self.pos].type != TokenType.EOF:
            self.pos += 1
        return t

    def _consume(self, tt: TokenType) -> Token | None:
        if self._current().type == tt:
            return self._advance()
        return None

    def parse_condition(self) -> ConditionNode:
        return self._disjunction()

    def _disjunction(self) -> ConditionNode:
        left = self._conjunction()
        if self._consume(TokenType.OR):
            children = [left, self._conjunction()]
            while self._consume(TokenType.OR):
                children.append(self._conjunction())
            return OrNode(children)
        return left

    def _conjunction(self) -> ConditionNode:
        left = self._unary()
        if self._consume(TokenType.AND):
            children = [left, self._unary()]
            while self._consume(TokenType.AND):
                children.append(self._unary())
            return AndNode(children)
        return left

    def _unary(self) -> ConditionNode:
        if self._consume(TokenType.NOT):
            return NotNode(self._unary())
        return self._primary()

    def _primary(self) -> ConditionNode:
        if self._consume(TokenType.LPAREN):
            node = self._disjunction()
            if not self._consume(TokenType.RPAREN):
                raise UnsupportedSigmaFeatureError("Missing closing parenthesis in condition")
            return node
        if self._current().type == TokenType.ONE:
            self._advance()
            if not self._consume(TokenType.OF):
                raise UnsupportedSigmaFeatureError("Expected 'of' after '1' in condition")
            rhs = self._primary()
            if isinstance(rhs, IdentNode):
                return OneOfNode(rhs.name)
            raise UnsupportedSigmaFeatureError("'1 of' requires a selection reference")
        if self._current().type == TokenType.ALL:
            self._advance()
            if not self._consume(TokenType.OF):
                raise UnsupportedSigmaFeatureError("Expected 'of' after 'all' in condition")
            rhs = self._primary()
            if isinstance(rhs, IdentNode):
                return AllOfNode(rhs.name)
            raise UnsupportedSigmaFeatureError("'all of' requires a selection reference")
        if self._current().type == TokenType.IDENT:
            t = self._advance()
            return IdentNode(t.value)
        raise UnsupportedSigmaFeatureError(f"Unexpected token in condition: {self._current()}")


def parse_condition_string(condition: str) -> ConditionNode:
    """Parse condition string to condition tree. Uses tokenizer + recursive descent."""
    _reject_unsupported_condition(condition)
    tokens = _tokenize_condition(condition)
    parser = _Parser(tokens)
    node = parser.parse_condition()
    if parser._current().type != TokenType.EOF:
        raise UnsupportedSigmaFeatureError("Unexpected tokens after condition")
    return node


# -----------------------------------------------------------------------------
# Resolve selection references to detection blocks
# -----------------------------------------------------------------------------


def _selection_keys_matching(detection: dict, pattern: str) -> list[str]:
    """Return detection keys that match pattern. pattern may end with *."""
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        return [k for k in detection if k != "condition" and k.startswith(prefix)]
    if pattern in detection and pattern != "condition":
        return [pattern]
    return []


def _resolve_selection_content(detection: dict, key: str) -> list[dict[str, Any]]:
    """Get selection block content as list of dicts. List in YAML -> OR; |all -> AND."""
    raw = detection.get(key)
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _resolve_node(node: ConditionNode, detection: dict) -> Any:
    """Convert parsed condition node to normalized structure with resolved selections.
    Output: {"and": [nodes]} | {"or": [nodes]} | {"not": node} | {"selection": list[dict]}
    """
    if isinstance(node, AndNode):
        return {"and": [_resolve_node(c, detection) for c in node.children]}
    if isinstance(node, OrNode):
        return {"or": [_resolve_node(c, detection) for c in node.children]}
    if isinstance(node, NotNode):
        return {"not": _resolve_node(node.child, detection)}
    if isinstance(node, OneOfNode):
        keys = _selection_keys_matching(detection, node.ident)
        if not keys:
            raise UnsupportedSigmaFeatureError(f"Selection not found: {node.ident}")
        # 1 of selection* -> OR of those selections
        blocks: list[dict] = []
        for k in sorted(keys):
            blocks.extend(_resolve_selection_content(detection, k))
        return {"or": [{"selection": [b]} for b in blocks]} if len(blocks) > 1 else {"selection": blocks}
    if isinstance(node, AllOfNode):
        keys = _selection_keys_matching(detection, node.ident)
        if not keys:
            raise UnsupportedSigmaFeatureError(f"Selection not found: {node.ident}")
        # all of selection* -> AND of those selections (each selection block AND of its atoms)
        parts = []
        for k in sorted(keys):
            blocks = _resolve_selection_content(detection, k)
            if blocks:
                parts.append({"selection": blocks})
        if not parts:
            raise UnsupportedSigmaFeatureError(f"Empty selection: {node.ident}")
        return {"and": parts} if len(parts) > 1 else parts[0]
    if isinstance(node, IdentNode):
        keys = _selection_keys_matching(detection, node.name)
        if not keys:
            raise UnsupportedSigmaFeatureError(f"Selection not found: {node.name}")
        if len(keys) == 1:
            blocks = _resolve_selection_content(detection, keys[0])
            return {"selection": blocks}
        # selection* with multiple keys -> OR of selections
        all_blocks: list[Any] = []
        for k in sorted(keys):
            blocks = _resolve_selection_content(detection, k)
            if blocks:
                all_blocks.append({"selection": blocks})
        return {"or": all_blocks} if len(all_blocks) > 1 else (all_blocks[0] if all_blocks else {"selection": []})
    raise UnsupportedSigmaFeatureError(f"Unknown node type: {type(node)}")


def normalize_detection(detection: dict) -> dict[str, Any]:
    """Normalize detection dict: parse condition, resolve selections, return tree for ast_builder.
    Raises UnsupportedSigmaFeatureError for unsupported features or missing condition.
    """
    if not isinstance(detection, dict):
        raise UnsupportedSigmaFeatureError("detection must be a dict")
    condition = detection.get("condition")
    if condition is None:
        raise UnsupportedSigmaFeatureError("Missing condition in detection")
    if isinstance(condition, list):
        raise UnsupportedSigmaFeatureError("List conditions not supported")
    cond_str = str(condition).strip()
    parsed = parse_condition_string(cond_str)
    return _resolve_node(parsed, detection)
