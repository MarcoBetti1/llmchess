import unittest
from unittest.mock import AsyncMock, patch

from src.llmchess_simple.game import GameConfig, GameRunner
from src.llmchess_simple.random_opponent import RandomOpponent


class PromptSystemTests(unittest.TestCase):
    def test_legal_move_system_simple_success_flow(self):
        cfg = GameConfig(prompt_system="legal-move-system-simple", game_log=False)
        runner = GameRunner(model="dummy", opponent=RandomOpponent(), cfg=cfg)

        async_mock_move = AsyncMock(return_value="e2e4")
        async_mock_yes = AsyncMock(return_value="yes")
        async_mock_move_second = AsyncMock(return_value="e2e4")

        with patch(
            "src.llmchess_simple.prompt_systems.legal_move_system_simple.LegalMoveSystemSimple._extract_candidate",
            async_mock_move,
        ), patch(
            "src.llmchess_simple.prompt_systems.legal_move_system_simple.LegalMoveSystemSimple._classify_legality",
            async_mock_yes,
        ), patch(
            "src.llmchess_simple.game.normalize_with_agent",
            async_mock_move_second,
        ):
            msgs_first = runner.build_llm_messages()
            self.assertIsNone(
                runner.step_llm_with_raw("I will play e2e4", msgs_first),
                "First stage should defer until legality check completes",
            )

            msgs_second = runner.build_llm_messages()
            self.assertIn("Proposed move", msgs_second[-1]["content"])

            result = runner.step_llm_with_raw("Yes, that move is legal.", msgs_second)
            self.assertIsNotNone(result)
            ok, uci, san, ms, meta = result

        self.assertTrue(ok)
        self.assertEqual(uci, "e2e4")
        self.assertEqual(san, "e4")
        self.assertIsInstance(ms, int)
        last_move = runner.ref.board.peek()
        self.assertEqual(last_move.uci(), "e2e4")
        self.assertEqual(meta.get("prompt_system"), "legal-move-system-simple")
        stages = meta.get("prompt_system_stages")
        self.assertIsInstance(stages, list)
        self.assertEqual(len(stages), 2)
        self.assertEqual(runner.records[-1]["uci"], "e2e4")


if __name__ == "__main__":
    unittest.main()
