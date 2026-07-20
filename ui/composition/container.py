from __future__ import annotations

from dataclasses import dataclass

from engine.arbiter.real_time_arbiter import RealTimeArbiter
from engine.game_engine import GameEngine
from engine.models.board import Board
from engine.rules.rule_engine import RuleEngine
from ui.config.app_config import DEFAULT_APP_CONFIG
from ui.interaction.board_mapper import BoardMapper
from ui.interaction.controller import Controller
from ui.state.game_facade import GameFacade
from ui.ui_components.banner import Banner
from ui.ui_components.game_animation import GameAnimationController
from ui.ui_components.moves_feed import MovesFeed
from ui.ui_components.score_panel import ScorePanel
from ui.ui_components.sound_player import SoundPlayer


@dataclass(frozen=True)
class AppContainer:
    facade: GameFacade
    controller: Controller
    mapper: BoardMapper
    moves: MovesFeed
    scores: ScorePanel
    banner: Banner
    sound: SoundPlayer
    anim: GameAnimationController


def build_container(board_lines: list[str]) -> AppContainer:
    board = Board(board_lines)
    engine = GameEngine(board, RuleEngine(), RealTimeArbiter(board))
    facade = GameFacade(engine)

    mapper = BoardMapper(
        cell_size=DEFAULT_APP_CONFIG.board.cell_size_px,
        rows=len(board_lines),
        cols=len(board_lines[0].split()),
    )
    controller = Controller(facade, mapper)

    moves = MovesFeed()
    scores = ScorePanel()
    banner = Banner()
    sound = SoundPlayer()
    anim = GameAnimationController()

    # Bind all subscribers to the facade's event bus.
    # Order matters: data components before visual ones so state is up-to-date
    # when the renderer reads it on the same frame.
    moves.bind(facade.subject)
    scores.bind(facade.subject)
    banner.bind(facade.subject)
    sound.bind(facade.subject)
    anim.bind(facade.subject)

    return AppContainer(
        facade=facade,
        controller=controller,
        mapper=mapper,
        moves=moves,
        scores=scores,
        banner=banner,
        sound=sound,
        anim=anim,
    )
