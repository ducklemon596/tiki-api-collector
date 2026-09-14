import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crawler"))

from utils.product import clean_description


class CleanDescriptionTests(unittest.TestCase):
    def test_normal_text_is_unchanged(self) -> None:
        self.assertEqual(clean_description("Normal product description."), "Normal product description.")

    def test_non_breaking_space_becomes_a_normal_space(self) -> None:
        self.assertEqual(clean_description("A\u00a0B"), "A B")

    def test_repeated_inline_spaces_are_collapsed(self) -> None:
        self.assertEqual(clean_description("A   product\t\tname"), "A product name")

    def test_spaces_around_newlines_are_removed(self) -> None:
        self.assertEqual(clean_description("First  \n\tSecond"), "First\nSecond")

    def test_spaced_paragraph_separator_is_normalized(self) -> None:
        self.assertEqual(clean_description("First\n \n   Second"), "First\n\nSecond")

    def test_three_or_more_newlines_become_one_paragraph_separator(self) -> None:
        self.assertEqual(clean_description("First\n\n\nSecond"), "First\n\nSecond")

    def test_none_and_empty_text_are_preserved(self) -> None:
        self.assertIsNone(clean_description(None))
        self.assertEqual(clean_description(""), "")

    def test_requested_example(self) -> None:
        self.assertEqual(
            clean_description("First paragraph. \n \n   Second paragraph.\n\n\nThird paragraph."),
            "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
        )


if __name__ == "__main__":
    unittest.main()
