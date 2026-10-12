"""Deterministic strategy-game rules and validation for the puzzle catalog."""

import re
from functools import lru_cache
from typing import Iterable, Optional, Tuple


def field(body: str, name: str) -> str:
    match = re.search(r"(?m)^\*\*" + re.escape(name) + r":\*\* (.+)$", body)
    if match is None:
        raise ValueError("strategy puzzle is missing {}".format(name))
    return match[1].strip()


def block(body: str, name: str) -> Tuple[str, ...]:
    match = re.search(
        r"(?ms)^\*\*" + re.escape(name) + r":\*\*\s*\n```[^\n]*\n(.*?)\n```", body,
    )
    if match is None:
        raise ValueError("strategy puzzle is missing {} block".format(name))
    return tuple(match[1].splitlines())


def starting_piles(body: str, name: str = "Starting piles") -> Tuple[int, ...]:
    text = field(body, name)
    if not re.fullmatch(r"\d+(?:, \d+)+", text):
        raise ValueError("starting piles must be comma-separated nonnegative integers")
    return tuple(int(value) for value in text.split(", "))


def nim_sum(piles: Iterable[int]) -> int:
    total = 0
    for pile in piles:
        if isinstance(pile, bool) or not isinstance(pile, int) or pile < 0:
            raise ValueError("Nim piles must be nonnegative integers")
        total ^= pile
    return total


def nim_winning_move(piles: Tuple[int, ...]) -> Optional[Tuple[int, int]]:
    total = nim_sum(piles)
    for index, pile in enumerate(piles):
        reduced = pile ^ total
        if reduced < pile:
            return index, reduced
    return None


def wythoff_moves(piles: Tuple[int, int]) -> Tuple[Tuple[int, int], ...]:
    first, second = piles
    return tuple(
        [(value, second) for value in range(first)]
        + [(first, value) for value in range(second)]
        + [(first - amount, second - amount) for amount in range(1, min(piles) + 1)]
    )


@lru_cache(maxsize=None)
def wythoff_winning(piles: Tuple[int, int]) -> bool:
    return any(not wythoff_winning(after) for after in wythoff_moves(piles))


def chomp_moves(rows: Tuple[int, ...]) -> Tuple[Tuple[int, ...], ...]:
    return tuple(
        tuple(length if index < row else min(length, column)
              for index, length in enumerate(rows))
        for row, length in enumerate(rows) for column in range(length)
        if (row, column) != (0, 0)
    )


@lru_cache(maxsize=None)
def chomp_winning(rows: Tuple[int, ...]) -> bool:
    # Biting the marked lower-left square loses immediately; only safe moves
    # are searched. With that square alone, the player to move has lost.
    return any(not chomp_winning(after) for after in chomp_moves(rows))


GoBoard = Tuple[str, ...]


def _validate_go_board(board: GoBoard, color: str) -> None:
    if (color not in ("B", "W") or not 2 <= len(board) <= 26
            or any(len(row) != len(board) or set(row) - set(".BW") for row in board)):
        raise ValueError("Go requires a square .BW board and a B/W player")


def go_cell(board: GoBoard, coordinate: str) -> Tuple[int, int]:
    size = len(board)
    if (not re.fullmatch(r"[A-Z][1-9]\d*", coordinate)
            or not 0 <= ord(coordinate[0]) - ord("A") < size
            or not 1 <= int(coordinate[1:]) <= size):
        raise ValueError("Go coordinate is outside the board: {}".format(coordinate))
    return ord(coordinate[0]) - ord("A"), size - int(coordinate[1:])


def _neighbors(size, x, y):
    return tuple((nx, ny) for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                 if 0 <= nx < size and 0 <= ny < size)


def go_group(board: GoBoard, cell: Tuple[int, int]):
    x, y = cell
    color = board[y][x]
    if color not in "BW":
        raise ValueError("Go group must start at a stone")
    stones, liberties = {cell}, set()
    pending = [cell]
    while pending:
        x, y = pending.pop()
        for nx, ny in _neighbors(len(board), x, y):
            if board[ny][nx] == ".":
                liberties.add((nx, ny))
            elif board[ny][nx] == color and (nx, ny) not in stones:
                stones.add((nx, ny))
                pending.append((nx, ny))
    return stones, liberties


def go_play(
    board: GoBoard, coordinate: str, color: str, history: Tuple[GoBoard, ...] = (),
) -> GoBoard:
    _validate_go_board(board, color)
    if coordinate == "pass":
        return board
    x, y = go_cell(board, coordinate)
    if board[y][x] != ".":
        raise ValueError("Go intersection is occupied")
    rows = [list(row) for row in board]
    rows[y][x] = color
    placed = tuple("".join(row) for row in rows)
    for neighbor in _neighbors(len(board), x, y):
        nx, ny = neighbor
        if placed[ny][nx] not in (".", color):
            stones, liberties = go_group(placed, neighbor)
            if not liberties:
                for cx, cy in stones:
                    rows[cy][cx] = "."
    result = tuple("".join(row) for row in rows)
    if not go_group(result, (x, y))[1]:
        raise ValueError("Go suicide is illegal")
    if result in history or result == board:
        raise ValueError("Go positional superko forbids repeating a board")
    return result


def go_legal_moves(board: GoBoard, color: str, history: Tuple[GoBoard, ...] = ()):
    _validate_go_board(board, color)
    for y, row in enumerate(board):
        for x, tile in enumerate(row):
            if tile != ".":
                continue
            coordinate = "{}{}".format(chr(ord("A") + x), len(board) - y)
            # Illegal game moves are deliberately excluded, not generation errors.
            try:
                after = go_play(board, coordinate, color, history)
            except ValueError:
                continue
            yield coordinate, after
    yield "pass", board


def validate_go_ladder(board: GoBoard, target: str, line: Tuple[str, ...], budget: int) -> None:
    _validate_go_board(board, "B")
    cell = go_cell(board, target)
    tx, ty = cell
    if board[ty][tx] != "W" or len(line) != budget * 2 - 1:
        raise ValueError("Go ladder needs a white target and an odd, budget-length solution")
    history = (board,)
    for index in range(0, len(line), 2):
        board = go_play(board, line[index], "B", history)
        history += (board,)
        if index == len(line) - 1:
            if board[ty][tx] == "W":
                raise ValueError("Go solution does not capture its target")
            return
        if board[ty][tx] != "W":
            raise ValueError("Go ladder captures before its stated final move")
        expected = line[index + 1]
        replies = dict(go_legal_moves(board, "W", history))
        if expected not in replies:
            raise ValueError("Go solution contains an illegal defense")
        for reply, after in replies.items():
            if reply == expected:
                continue
            _, liberties = go_group(after, cell)
            if len(liberties) != 1:
                raise ValueError("Go ladder has an unhandled defending move: " + reply)
            x, y = next(iter(liberties))
            capture = "{}{}".format(chr(ord("A") + x), len(board) - y)
            captured = go_play(after, capture, "B", history + (after,))
            if captured[ty][tx] == "W":
                raise ValueError("Go defender can escape the claimed ladder")
        board = replies[expected]
        if index + 2 < len(line) - 1 and len(go_group(board, cell)[1]) < 2:
            raise ValueError("Go solution claims a saving extension that loses immediately")
        history += (board,)


def validate_strategy_game(body: str) -> None:
    game = field(body, "Game")
    if game == "Normal-play Nim":
        piles = starting_piles(body)
        if len(piles) not in (3, 4) or any(not 1 <= pile <= 8 for pile in piles) or not nim_sum(piles):
            raise ValueError("Nim needs 3-4 positive piles of at most 8 with a nonzero nim-sum")
        move = field(body, "Winning opening")
        opening = nim_winning_move(piles)
        if opening is None or move != "{} -> {}".format(opening[0] + 1, opening[1]):
            raise ValueError("Nim opening must be the first xor-zero reduction")
    elif game == "Chess":
        fen = field(body, "FEN")
        parts = fen.split()
        if (len(parts) != 6 or parts[1] != "w" or len(parts[0].split("/")) != 8
                or parts[0].count("K") != 1 or parts[0].count("k") != 1):
            raise ValueError("chess puzzle needs a complete White-to-move FEN with both kings")
        budget = int(field(body, "Move budget"))
        if not 3 <= budget <= 6:
            raise ValueError("chess move budget must be 3 through 6")
        lines = block(body, "Winning lines")
        if not lines or any(len(line.split()) > 2 * budget - 1 or not line.endswith("#") for line in lines):
            raise ValueError("chess solution must include mating lines within its move budget")
    elif game == "Capture Go":
        board = block(body, "Board")
        line = field(body, "Winning line").split()
        budget = int(field(body, "Move budget"))
        if not 3 <= budget <= 6:
            raise ValueError("Go move budget must be 3 through 6")
        validate_go_ladder(board, field(body, "Target"), tuple(line), budget)
    elif game == "Wythoff":
        piles = starting_piles(body)
        if len(piles) != 2 or any(not 1 <= value <= 9 for value in piles):
            raise ValueError("Wythoff needs two piles with 1-9 tokens")
        if not wythoff_winning(piles):
            raise ValueError("Wythoff must start with a first-player win")
    elif game == "Chomp":
        rows = starting_piles(body, "Starting rows")
        if rows != (3, 3, 3) or not chomp_winning(rows):
            raise ValueError("the Chomp puzzle requires the winning 3-by-3 starting tablet")
    else:
        raise ValueError("unknown strategy game: " + game)
