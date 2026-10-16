import io
import itertools
import os
import random
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

import chess
import chess.pgn

from dungeon_encounters import encounter_document
from dungeon_games import (
    block, chomp_moves, chomp_winning, field, go_cell, go_legal_moves,
    go_play, nim_sum, nim_winning_move, starting_piles, validate_go_ladder,
    validate_strategy_game, wythoff_moves, wythoff_winning,
)
from dungeon_map import GenerationOptions
from dungeon_puzzles import PUZZLE_COUNT, generate_adventure, load_puzzles, validate_puzzle_dungeon


HISTORICAL_SCORES = {
    35: (
        "1. e4 e5 2. f4 exf4 3. Bc4 Qh4+ 4. Kf1 b5 5. Bxb5 Nf6 "
        "6. Nf3 Qh6 7. d3 Nh5 8. Nh4 Qg5 9. Nf5 c6 10. g4 Nf6 "
        "11. Rg1 cxb5 12. h4 Qg6 13. h5 Qg5 14. Qf3 Ng8 15. Bxf4 Qf6 "
        "16. Nc3 Bc5 17. Nd5 Qxb2 18. Bd6 Bxg1 19. e5 Qxa1+ 20. Ke2 Na6"
    ),
    36: (
        "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4 Bxb4 5. c3 Ba5 6. d4 exd4 "
        "7. O-O d3 8. Qb3 Qf6 9. e5 Qg6 10. Re1 Nge7 11. Ba3 b5 12. Qxb5 Rb8 "
        "13. Qa4 Bb6 14. Nbd2 Bb7 15. Ne4 Qf5 16. Bxd3 Qh5 17. Nf6+ gxf6 "
        "18. exf6 Rg8 19. Rad1 Qxf3 20. Rxe7+ Nxe7"
    ),
}


@lru_cache(maxsize=200000)
def forced_mate(fen, moves):
    board = chess.Board(fen)
    legal = sorted(board.legal_moves, key=lambda move: (not board.gives_check(move), move.uci()))
    if not legal:
        return board.turn == chess.BLACK and board.is_check()
    if moves == 0 and board.turn == chess.WHITE:
        return False
    white = board.turn == chess.WHITE
    for move in legal:
        board.push(move)
        wins = forced_mate(board.fen(), moves - int(white))
        board.pop()
        if white and wins:
            return True
        if not white and not wins:
            return False
    return not white


class StrategyGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_puzzles()
        cls.games = {p.number: p for p in cls.catalog if "**Game:**" in p.body}

    def test_nim_invariant_defeats_every_reply_within_the_starting_heaps(self):
        for number in (31, 32, 33, 34):
            body = self.games[number].body
            piles = starting_piles(body)
            with self.subTest(puzzle=number):
                self.assertNotEqual(nim_sum(piles), 0)
                index, reduced = nim_winning_move(piles)
                opening = piles[:index] + (reduced,) + piles[index + 1:]
                self.assertEqual(nim_sum(opening), 0)
                self.assertEqual(field(body, "Winning opening"), "{} -> {}".format(index + 1, reduced))
                for balanced in itertools.product(*(range(pile + 1) for pile in piles)):
                    if nim_sum(balanced):
                        continue
                    for index, pile in enumerate(balanced):
                        for amount in range(pile):
                            reply = balanced[:index] + (amount,) + balanced[index + 1:]
                            self.assertNotEqual(nim_sum(reply), 0)
                            target, value = nim_winning_move(reply)
                            self.assertLess(value, reply[target])
                            restored = reply[:target] + (value,) + reply[target + 1:]
                            self.assertEqual(nim_sum(restored), 0)

    def test_invalid_nim_start_or_advertised_opening_is_rejected(self):
        body = self.games[31].body
        for replacement in ("3, 4, 7", "0, 4, 5", "3, 4, 9", "3, 4"):
            with self.subTest(piles=replacement), self.assertRaises(ValueError):
                validate_strategy_game(body.replace("**Starting piles:** 3, 4, 5",
                                                    "**Starting piles:** " + replacement))
        with self.assertRaisesRegex(ValueError, "opening"):
            validate_strategy_game(body.replace("**Winning opening:** 1 -> 1",
                                                "**Winning opening:** 2 -> 0"))

    def test_wythoff_balanced_positions_cover_every_guardian_reply(self):
        start = starting_piles(self.games[39].body)
        losing = {(0, 0), (1, 2), (2, 1), (3, 5)}
        for state in itertools.product(range(start[0] + 1), range(start[1] + 1)):
            self.assertEqual(not wythoff_winning(state), state in losing)
        opening = (3, 5)
        self.assertIn(opening, wythoff_moves(start))
        for reply in wythoff_moves(opening):
            self.assertTrue(losing.intersection(wythoff_moves(reply)))

    def test_chomp_mirror_strategy_works_after_every_safe_bite(self):
        start = starting_piles(self.games[40].body, "Starting rows")
        self.assertIn((3, 1, 1), chomp_moves(start))
        self.assertFalse(chomp_winning((3, 1, 1)))
        for arm in (1, 2, 3):
            balanced = (arm,) + tuple(1 if row < arm else 0 for row in (1, 2))
            for reply in chomp_moves(balanced):
                remaining_arm = min(reply[0], sum(length > 0 for length in reply))
                restored = (remaining_arm,) + tuple(
                    1 if row < remaining_arm else 0 for row in (1, 2)
                )
                self.assertIn(restored, chomp_moves(reply))
                self.assertFalse(chomp_winning(restored))
        self.assertEqual(chomp_moves((1, 0, 0)), ())

    def test_go_ladders_cover_every_defense_including_pass(self):
        for number in (37, 38):
            body = self.games[number].body
            board = block(body, "Board")
            target = field(body, "Target")
            line = tuple(field(body, "Winning line").split())
            budget = int(field(body, "Move budget"))
            with self.subTest(puzzle=number):
                validate_go_ladder(board, target, line, budget)
                cell = go_cell(board, target)
                history = (board,)
                for index in range(0, len(line), 2):
                    board = go_play(board, line[index], "B", history)
                    history += (board,)
                    if index == len(line) - 1:
                        self.assertNotEqual(board[cell[1]][cell[0]], "W")
                        break
                    replies = dict(go_legal_moves(board, "W", history))
                    self.assertIn("pass", replies)
                    survivors = []
                    for move, after in replies.items():
                        immediate_captures = [
                            next_board for _, next_board in go_legal_moves(after, "B", history + (after,))
                            if next_board[cell[1]][cell[0]] != "W"
                        ]
                        if not immediate_captures:
                            survivors.append(move)
                    expected = [line[index + 1]] if index + 2 < len(line) - 1 else []
                    self.assertEqual(survivors, expected)
                    board = replies[line[index + 1]]
                    history += (board,)

    def test_go_rejects_ladder_breaker_suicide_and_repeated_positions(self):
        body = self.games[38].body
        board = block(body, "Board")
        broken = go_play(board, "E5", "W")
        with self.assertRaises(ValueError):
            validate_go_ladder(broken, field(body, "Target"),
                               tuple(field(body, "Winning line").split()), 5)
        with self.assertRaisesRegex(ValueError, "suicide"):
            go_play((".....", "..B..", ".B.B.", "..B..", "....."), "C3", "W")
        after = go_play(board, "A1", "B")
        with self.assertRaisesRegex(ValueError, "superko"):
            go_play(board, "A1", "B", (after,))

    def verify_chess_tree(self, board, lines, moves):
        if all(not line for line in lines):
            self.assertTrue(board.is_checkmate())
            self.assertEqual(board.turn, chess.BLACK)
            return
        self.assertTrue(all(lines))
        grouped = {}
        for line in lines:
            grouped.setdefault(line[0], []).append(line[1:])
        if board.turn == chess.BLACK:
            self.assertEqual({board.parse_san(move) for move in grouped}, set(board.legal_moves))
        else:
            self.assertEqual(len(grouped), 1)
            self.assertGreater(moves, 0)
            moves -= 1
        for move, suffixes in grouped.items():
            board.push_san(move)
            self.verify_chess_tree(board, suffixes, moves)
            board.pop()

    def test_chess_positions_match_historical_scores_diagrams_and_complete_mating_trees(self):
        for number, pgn in HISTORICAL_SCORES.items():
            body = self.games[number].body
            fen = field(body, "FEN")
            with self.subTest(puzzle=number):
                recorded = chess.pgn.read_game(io.StringIO(pgn))
                self.assertEqual(recorded.errors, [])
                self.assertEqual(recorded.end().board().fen(), fen)
                board = chess.Board(fen)
                self.assertTrue(board.is_valid())
                self.assertEqual(tuple(str(board).replace(" ", "").splitlines()), block(body, "Board"))
                self.verify_chess_tree(board, [line.split() for line in block(body, "Winning lines")],
                                       int(field(body, "Solution length" if number == 35 else "Move budget")))

    def test_chess_mates_are_forced_in_exactly_the_claimed_solution_lengths(self):
        for number in HISTORICAL_SCORES:
            body = self.games[number].body
            fen = field(body, "FEN")
            budget = int(field(body, "Solution length" if number == 35 else "Move budget"))
            with self.subTest(puzzle=number):
                self.assertFalse(forced_mate(fen, budget - 1))
                self.assertTrue(forced_mate(fen, budget))
                forced_mate.cache_clear()

    def test_unlimited_chess_game_validates_solution_without_a_move_deadline(self):
        body = self.games[35].body
        self.assertNotIn("**Move budget:**", body)
        validate_strategy_game(body)
        with self.assertRaisesRegex(ValueError, "Solution length"):
            validate_strategy_game(body.replace("**Solution length:** 3\n", ""))
        with self.assertRaisesRegex(ValueError, "stated length"):
            validate_strategy_game(body.replace("Bxe7#", "Bxe7"))


class StrategyPlacementTests(unittest.TestCase):
    def test_cli_writes_all_strategy_games_without_runtime_chess_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "games.svg"
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            script = Path(__file__).resolve().with_name("generate_dungeon_map.py")
            result = subprocess.run(
                [sys.executable, "-S", str(script), "--seed", "42", "--width", "24",
                 "--height", "16", "--levels", "4", "--puzzle-probability", "1",
                 "--max-puzzles-per-level", str(PUZZLE_COUNT), "--output", str(output)],
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            key = output.with_name("games-encounters.md").read_text(encoding="utf-8")
            self.assertEqual(key.count("**Game:**"), 10)
            self.assertEqual(key.count("**Solution:**"), PUZZLE_COUNT)
            self.assertIn("**FEN:**", key)
            self.assertIn("**Winning line:** B4 C3 D3 C4 C5 D4 E4 D5 E5", key)
            self.assertEqual(len(list(Path(directory).iterdir())), 10)

    def test_harder_chess_and_go_wait_for_deeper_levels_without_repeats(self):
        catalog = [p for p in load_puzzles() if p.number in (35, 36, 37, 38)]
        with patch("dungeon_puzzles.load_puzzles", return_value=tuple(catalog)):
            dungeon, keys = generate_adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=4),
                puzzle_probability=1, max_puzzles_per_level=4,
            )
        self.assertEqual([{p.definition.number for p in key.puzzles} for key in keys],
                         [{35, 37}, set(), set(), {36, 38}])
        self.assertIn("eligible at this depth", " ".join(dungeon.levels[1].layout_notes))
        validate_puzzle_dungeon(dungeon, keys)
        markdown = encounter_document(dungeon, keys, 11)
        for puzzle in catalog:
            self.assertIn(puzzle.body, markdown)
        for puzzle in keys[-1].puzzles:
            self.assertIsNotNone(puzzle.gate)
            self.assertIsNone(puzzle.next_level)

    def test_unused_shallow_game_does_not_reappear_below_its_level_range(self):
        seed = None
        for candidate in range(1000):
            rng = random.Random("{}:puzzles".format(candidate))
            rolls = [rng.random() for _ in range(4)]
            if all(roll >= 0.35 for roll in rolls[:3]) and rolls[3] < 0.35:
                seed = candidate
                break
        self.assertIsNotNone(seed)
        catalog = [p for p in load_puzzles() if p.number == 35]
        with patch("dungeon_puzzles.load_puzzles", return_value=tuple(catalog)):
            dungeon, keys = generate_adventure(
                GenerationOptions(seed=seed, width=30, height=24, levels=4),
                puzzle_probability=0.35, max_puzzles_per_level=1,
            )
        self.assertFalse(any(key.puzzles for key in keys))
        self.assertIn("1 successes", " ".join(dungeon.levels[-1].layout_notes))
        self.assertIn("eligible at this depth", " ".join(dungeon.levels[-1].layout_notes))

    def test_depth_ineligible_definitions_are_rejected_by_dungeon_validator(self):
        catalog = [p for p in load_puzzles() if p.number == 36]
        with patch("dungeon_puzzles.load_puzzles", return_value=tuple(catalog)):
            dungeon, keys = generate_adventure(
                GenerationOptions(seed=42, width=30, height=24, levels=4),
                puzzle_probability=1, max_puzzles_per_level=1,
            )
        self.assertEqual([len(key.puzzles) for key in keys], [0, 0, 0, 1])
        placed = keys[-1].puzzles[0]
        bad = replace(placed, definition=replace(placed.definition, min_level=5))
        keys = keys[:-1] + (replace(keys[-1], puzzles=(bad,)),)
        with self.assertRaisesRegex(ValueError, "not eligible"):
            validate_puzzle_dungeon(dungeon, keys)


if __name__ == "__main__":
    unittest.main()
