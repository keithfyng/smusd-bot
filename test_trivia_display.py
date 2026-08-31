import unittest

from keyboards import build_question_keyboard, build_revealed_keyboard
from scheduler import format_question_text


class TriviaDisplayTests(unittest.TestCase):
    def setUp(self):
        self.options = [
            "A very long first option that would be truncated in a Telegram button",
            "Second <option>",
            "Third & final-ish option",
            "Fourth *Markdown-looking* option",
        ]

    def test_question_text_contains_full_html_safe_options(self):
        text = format_question_text("Which <answer> is right & why?", self.options)

        self.assertIn("Which &lt;answer&gt; is right &amp; why?", text)
        self.assertIn(f"A) {self.options[0]}", text)
        self.assertIn("B) Second &lt;option&gt;", text)
        self.assertIn("C) Third &amp; final-ish option", text)
        self.assertIn("D) Fourth *Markdown-looking* option", text)

    def test_open_keyboard_uses_short_labels_and_preserves_callbacks(self):
        keyboard = build_question_keyboard(42, self.options)

        self.assertEqual(
            [row[0].text for row in keyboard.inline_keyboard],
            ["A", "B", "C", "D"],
        )
        self.assertEqual(
            [row[0].callback_data for row in keyboard.inline_keyboard],
            ["vote_42_0", "vote_42_1", "vote_42_2", "vote_42_3"],
        )

    def test_revealed_keyboard_uses_compact_results(self):
        keyboard = build_revealed_keyboard(
            42,
            self.options,
            correct_indices=[1],
            vote_counts={0: 1, 1: 3},
        )

        self.assertEqual(
            [row[0].text for row in keyboard.inline_keyboard],
            ["❌ A — 1 (25%)", "✅ B — 3 (75%)", "❌ C — 0 (0%)", "❌ D — 0 (0%)"],
        )
        self.assertEqual(
            [row[0].callback_data for row in keyboard.inline_keyboard],
            ["vote_42_0", "vote_42_1", "vote_42_2", "vote_42_3"],
        )


if __name__ == "__main__":
    unittest.main()
