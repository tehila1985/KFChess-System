"""
End-to-end tests that drive GameRunner.run() exactly as main.py does.
Input is fed via StringIO; output is captured via capsys.
"""
import io
import pytest
from engine.game_runner import GameRunner


def run(input_text: str, capsys) -> str:
    GameRunner().run(io.StringIO(input_text))
    return capsys.readouterr().out.strip()


# ── Board parsing ──────────────────────────────────────────────────────

class TestBoardParsing:
    def test_parse_empty_board_3x3(self, capsys):
        out = run(
            "Board:\n. . .\n. . .\n. . .\nCommands:\nprint board\n", capsys
        )
        assert out == ". . .\n. . .\n. . ."

    def test_parse_rectangular_board_3x4(self, capsys):
        out = run(
            "Board:\nwK . . bK\n. . . .\nwR . . bR\nCommands:\nprint board\n", capsys
        )
        assert out == "wK . . bK\n. . . .\nwR . . bR"

    def test_parse_piece_tokens_and_colors(self, capsys):
        out = run(
            "Board:\nwK . bQ\n. wN .\nbP . wR\nCommands:\nprint board\n", capsys
        )
        assert out == "wK . bQ\n. wN .\nbP . wR"

    def test_reject_unknown_token_no_commands(self, capsys):
        out = run("Board:\nwK xZ\n. .\nCommands:\n", capsys)
        assert out == "ERROR UNKNOWN_TOKEN"

    def test_reject_row_width_mismatch_no_commands(self, capsys):
        out = run("Board:\nwK . .\n. bK\nCommands:\n", capsys)
        assert out == "ERROR ROW_WIDTH_MISMATCH"

    def test_reject_unknown_token_with_print(self, capsys):
        out = run("Board:\nwK xZ\n. .\nCommands:\nprint board\n", capsys)
        assert out == "ERROR UNKNOWN_TOKEN"

    def test_reject_row_width_mismatch_with_print(self, capsys):
        out = run("Board:\nwK . .\n. bK\nCommands:\nprint board\n", capsys)
        assert out == "ERROR ROW_WIDTH_MISMATCH"


# ── Click / selection ──────────────────────────────────────────────────

class TestClickSelection:
    def test_select_piece_by_center_click(self, capsys):
        out = run(
            "Board:\nwK . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 150 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. wK .\n. . ."

    def test_click_empty_cell_does_not_select(self, capsys):
        out = run(
            "Board:\nwK . .\n. . .\n. . .\nCommands:\nclick 150 150\nclick 250 250\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wK . .\n. . .\n. . ."

    def test_click_outside_board_is_ignored(self, capsys):
        out = run(
            "Board:\nwK . .\n. . .\n. . .\nCommands:\nclick 350 50\nclick -10 50\nprint board\n",
            capsys,
        )
        assert out == "wK . .\n. . .\n. . ."

    def test_clicking_another_piece_replaces_selection(self, capsys):
        out = run(
            "Board:\nwR . wK\n. . .\nCommands:\nclick 50 50\nclick 250 50\nclick 250 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wR . .\n. . wK"


# ── Movement rules ─────────────────────────────────────────────────────

class TestMovementRules:
    def test_king_one_step_valid(self, capsys):
        out = run(
            "Board:\nwK . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 150 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. wK .\n. . ."

    def test_king_two_steps_invalid(self, capsys):
        out = run(
            "Board:\nwK . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 250 250\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wK . .\n. . .\n. . ."

    def test_rook_straight_valid(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_rook_diagonal_invalid(self, capsys):
        out = run(
            "Board:\nwR . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 150 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wR . .\n. . .\n. . ."

    def test_bishop_diagonal_valid(self, capsys):
        out = run(
            "Board:\nwB . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 250 250\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. . wB"

    def test_knight_L_valid(self, capsys):
        out = run(
            "Board:\nwN . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 150 250\nwait 3000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. wN ."

    def test_queen_diagonal_valid(self, capsys):
        out = run(
            "Board:\nwQ . .\n. . .\n. . .\nCommands:\nclick 50 50\nclick 250 250\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. . wQ"


# ── Path blocking ──────────────────────────────────────────────────────

class TestPathBlocking:
    def test_rook_blocked_by_own_piece(self, capsys):
        out = run(
            "Board:\nwR wP .\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == "wR wP ."

    def test_bishop_blocked_by_own_piece(self, capsys):
        out = run(
            "Board:\nwB . .\n. wP .\n. . .\nCommands:\nclick 50 50\nclick 250 250\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == "wB . .\n. wP .\n. . ."

    def test_knight_jumps_over_blockers(self, capsys):
        out = run(
            "Board:\nwN wP .\nwP . .\n. . .\nCommands:\nclick 50 50\nclick 150 250\nwait 3000\nprint board\n",
            capsys,
        )
        assert out == ". wP .\nwP . .\n. wN ."

    def test_cannot_capture_own_piece(self, capsys):
        out = run(
            "Board:\nwR . wP\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == "wR . wP"

    def test_rook_captures_enemy_at_destination(self, capsys):
        out = run(
            "Board:\nwR . bR\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_pawn_cannot_capture_forward(self, capsys):
        out = run(
            "Board:\n. bR .\n. wP .\n. . .\nCommands:\nclick 150 150\nclick 150 50\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". bR .\n. wP .\n. . ."

    def test_cannot_start_move_through_friendly_piece(self, capsys):
        out = run(
            "Board:\n. . .\nwR wP .\n. . .\nCommands:\nclick 50 150\nclick 250 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\nwR wP .\n. . ."

    def test_knight_cannot_land_on_friendly_piece(self, capsys):
        out = run(
            "Board:\n. wP .\n. . .\nwN . .\nCommands:\nclick 50 250\nclick 150 50\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". wP .\n. . .\nwN . ."


# ── Timing ─────────────────────────────────────────────────────────────

class TestTiming:
    def test_one_cell_move_before_arrival_board_unchanged(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 150 50\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wR . ."

    def test_two_cell_move_before_and_after_arrival(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 250 50\nwait 1000\nprint board\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == "wR . .\n. . wR"

    def test_moving_piece_ignores_redirect(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 250 50\nwait 1000\nclick 50 50\nclick 150 50\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_no_cooldown_state_in_common_route(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 150 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". wR ."

    def test_can_move_again_after_arrival_without_cooldown(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 150 50\nwait 2000\nclick 150 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_piece_is_ready_after_arrival_without_cooldown(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 150 50\nwait 2000\nclick 150 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_premove_does_not_execute_in_common_route(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 150 50\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". wR ."


# ── Collision ──────────────────────────────────────────────────────────

class TestCollision:
    def test_opposite_colors_do_not_move_concurrently_in_common_route(self, capsys):
        out = run(
            "Board:\nwR . .\n. . .\nbR . .\nCommands:\nclick 50 50\nclick 250 50\nclick 50 250\nclick 250 250\nwait 4000\nprint board\n",
            capsys,
        )
        assert out == ". . wR\n. . .\nbR . ."

    def test_enemy_collision_white_started_first(self, capsys):
        out = run(
            "Board:\nwR . . bR\nCommands:\nclick 50 50\nclick 350 50\nclick 350 50\nclick 50 50\nwait 4000\nprint board\n",
            capsys,
        )
        assert out == ". . . wR"

    def test_enemy_collision_black_started_first(self, capsys):
        out = run(
            "Board:\nwR . . bR\nCommands:\nclick 350 50\nclick 50 50\nclick 50 50\nclick 350 50\nwait 4000\nprint board\n",
            capsys,
        )
        assert out == "bR . . ."

    def test_dynamic_block_tactic_not_in_common_route(self, capsys):
        out = run(
            "Board:\n. . . .\nwQ . . bK\n. . bP .\n. . . .\nCommands:\nclick 50 150\nclick 350 150\nwait 200\nclick 250 250\nclick 250 150\nwait 3000\nprint board\n",
            capsys,
        )
        assert out == ". . . .\n. . . wQ\n. . bP .\n. . . ."


# ── Game over ──────────────────────────────────────────────────────────

class TestGameOver:
    def test_king_capture_ends_game(self, capsys):
        out = run(
            "Board:\nwR . bK\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_no_moves_after_game_over(self, capsys):
        out = run(
            "Board:\nwR . bK\nbR . .\nCommands:\nclick 50 50\nclick 250 50\nwait 2000\nclick 50 150\nclick 150 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . wR\nbR . ."


# ── Pawn special moves ─────────────────────────────────────────────────

class TestPawnSpecial:
    def test_white_pawn_double_from_start_valid(self, capsys):
        out = run(
            "Board:\n. . .\n. . .\n. . .\n. wP .\nCommands:\nclick 150 350\nclick 150 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. wP .\n. . .\n. . ."

    def test_black_pawn_double_from_start_valid(self, capsys):
        out = run(
            "Board:\n. bP .\n. . .\n. . .\n. . .\nCommands:\nclick 150 50\nclick 150 250\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. bP .\n. . ."

    def test_white_pawn_double_blocked_invalid(self, capsys):
        out = run(
            "Board:\n. . .\n. . .\n. bR .\n. wP .\nCommands:\nclick 150 350\nclick 150 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. bR .\n. wP ."

    def test_white_pawn_double_from_non_start_invalid(self, capsys):
        out = run(
            "Board:\n. . .\n. . .\n. wP .\n. . .\nCommands:\nclick 150 250\nclick 150 50\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . .\n. wP .\n. . ."

    def test_white_pawn_promotes_to_queen(self, capsys):
        out = run(
            "Board:\n. . .\n. wP .\nCommands:\nclick 150 150\nclick 150 50\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". wQ .\n. . ."

    def test_black_pawn_promotes_to_queen(self, capsys):
        out = run(
            "Board:\n. bP .\n. . .\nCommands:\nclick 150 50\nclick 150 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. bQ ."

    def test_promoted_queen_moves_diagonal(self, capsys):
        out = run(
            "Board:\n. . .\n. wP .\n. . .\nCommands:\nclick 150 150\nclick 150 50\nwait 1000\nclick 150 50\nclick 250 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. . wQ\n. . ."


# ── Jump ───────────────────────────────────────────────────────────────

class TestJump:
    def test_jump_lands_same_square(self, capsys):
        out = run(
            "Board:\n. . .\n. wK .\n. . .\nCommands:\njump 150 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . .\n. wK .\n. . ."

    def test_airborne_piece_captures_arriving_enemy(self, capsys):
        out = run(
            "Board:\n. . .\nwK bR .\n. . .\nCommands:\njump 50 150\nclick 150 150\nclick 50 150\nwait 2000\nprint board\n",
            capsys,
        )
        assert out == ". . .\nwK . .\n. . ."

    def test_jump_too_late_does_not_save_piece(self, capsys):
        out = run(
            "Board:\n. . .\nwK bR .\n. . .\nCommands:\nclick 150 150\nclick 50 150\nwait 2000\njump 50 150\nprint board\n",
            capsys,
        )
        assert out == ". . .\nbR . .\n. . ."

    def test_enemy_arrives_after_landing_captures_normally(self, capsys):
        out = run(
            "Board:\n. . . .\nwK . . bR\n. . . .\nCommands:\njump 50 150\nwait 1000\nclick 350 150\nclick 50 150\nwait 3000\nprint board\n",
            capsys,
        )
        assert out == ". . . .\nbR . . .\n. . . ."

    def test_cannot_jump_while_moving(self, capsys):
        out = run(
            "Board:\nwR . .\nCommands:\nclick 50 50\nclick 250 50\nwait 500\njump 50 50\nwait 1500\nprint board\n",
            capsys,
        )
        assert out == ". . wR"

    def test_airborne_capture_only_enemy(self, capsys):
        out = run(
            "Board:\n. . .\nwK wR .\n. . .\nCommands:\njump 50 150\nclick 150 150\nclick 50 150\nwait 1000\nprint board\n",
            capsys,
        )
        assert out == ". . .\nwK wR .\n. . ."
