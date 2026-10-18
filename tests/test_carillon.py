import contextlib
import io
import os
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import carillon  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "demo-minor.method")


def run(argv):
    """Run the CLI, returning (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = carillon.main(argv)
    return code, out.getvalue(), err.getvalue()


def write_method(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".method", delete=False, encoding="utf-8")
    handle.write(text)
    handle.close()
    return handle.name


class ChangePermutationTests(unittest.TestCase):
    def test_cross_change_swaps_adjacent_pairs(self):
        self.assertEqual(carillon.change_permutation((), 4), (1, 0, 3, 2))

    def test_places_stay_and_the_rest_pair_up(self):
        # 1 and 4 make places, so 2 and 3 swap: 1234 -> 1324
        src = carillon.change_permutation((1, 4), 4)
        self.assertEqual(src, (0, 2, 1, 3))

    def test_odd_stage_last_bell_is_implicit_place(self):
        # 12345 -> 21435 with the 5 staying put
        self.assertEqual(carillon.change_permutation((), 5), (1, 0, 3, 2, 4))

    def test_six_bell_change_16(self):
        row = (1, 2, 3, 4, 5, 6)
        change = carillon.make_change("16", (1, 6), 6)
        self.assertEqual(carillon.rows_text(carillon.apply_change(row, change)), "132546")

    def test_unpairable_position_is_an_error(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.change_permutation((1,), 4)
        self.assertIn("position 4", caught.exception.message)


class NotationTests(unittest.TestCase):
    def test_x_and_digit_runs_form_separate_changes(self):
        self.assertEqual(
            carillon.parse_notation("x16x14", 6),
            [("x", ()), ("16", (1, 6)), ("x", ()), ("14", (1, 4))],
        )

    def test_dash_and_separators_are_accepted(self):
        self.assertEqual(carillon.parse_notation("-, 16 . x", 6)[0], ("x", ()))
        self.assertEqual(len(carillon.parse_notation("-, 16 . x", 6)), 3)

    def test_bells_ten_to_twelve_use_0_E_T(self):
        self.assertEqual(carillon.parse_notation("0ET", 12)[0][1], (10, 11, 12))

    def test_place_outside_stage_is_rejected(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_notation("x17", 6)
        self.assertIn("outside stage 6", caught.exception.message)

    def test_places_must_be_ascending(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_notation("61", 6)
        self.assertIn("strictly ascending", caught.exception.message)

    def test_unknown_character_is_reported(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_notation("1?", 6)
        self.assertIn("'?'", caught.exception.message)


class MethodFileTests(unittest.TestCase):
    def test_parses_crlf_and_comments(self):
        method = carillon.parse_method("# note\r\nname = Test\r\nstage = 4 # four\r\nlead = x\r\n")
        self.assertEqual((method.name, method.stage, len(method.lead)), ("Test", 4, 1))

    def test_missing_key_is_reported(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_method("lead = x\n")
        self.assertIn("'stage'", caught.exception.message)

    def test_duplicate_key_points_at_the_second_line(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_method("stage = 4\nlead = x\nstage = 6\n")
        self.assertEqual(caught.exception.line, 3)
        self.assertIn("line 1", caught.exception.message)

    def test_unknown_key_and_bad_stage_are_line_numbered(self):
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_method("stage = 4\nlead = x\ncolour = red\n")
        self.assertEqual(caught.exception.line, 3)
        with self.assertRaises(carillon.CarillonError) as caught:
            carillon.parse_method("stage = 1\nlead = x\n")
        self.assertEqual(caught.exception.line, 1)


class CourseTests(unittest.TestCase):
    def test_cross_lead_returns_to_rounds_after_two_changes(self):
        method = carillon.parse_method("stage = 4\nlead = x\n")
        rows = [carillon.rows_text(row) for row in carillon.plain_course(method)]
        self.assertEqual(rows, ["1234", "2143", "1234"])

    def test_two_change_lead_course_is_eight_changes_and_true(self):
        method = carillon.parse_method("stage = 4\nlead = x14\n")
        rows = carillon.plain_course(method)
        self.assertEqual(
            [carillon.rows_text(row) for row in rows],
            ["1234", "2143", "2413", "4231", "4321", "3412", "3142", "1324", "1234"],
        )
        self.assertEqual(carillon.repeated_rows(rows), [])

    def test_repeated_row_is_found_with_both_indexes(self):
        # The last element is the closing rounds, so it is not compared.
        rows = [(1, 2), (2, 1), (1, 2), (2, 1), (1, 2)]
        self.assertEqual(carillon.repeated_rows(rows), [(0, 2), (1, 3)])

    def test_false_method_is_detected_by_check(self):
        # Row 2413 is reached twice before the course returns to rounds.
        path = write_method("stage = 4\nlead = x14x\n")
        try:
            code, out, _ = run(["check", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, carillon.EXIT_FALSE)
        self.assertIn("FALSE", out)

    def test_summary_numbers_for_cross_lead(self):
        method = carillon.Method("t", 4, (carillon.make_change("x", (), 4),))
        summary = carillon.build_summary(method)
        self.assertEqual(summary["distinct_rows"], 2)
        self.assertEqual(summary["possible_rows"], 24)
        self.assertEqual(summary["extent_percent"], 8.33)
        self.assertTrue(summary["true"])


class FormatTests(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(carillon.format_duration(15000), "4:10:00")
        self.assertEqual(carillon.format_duration(125), "2:05")

    def test_fractions(self):
        self.assertEqual(carillon.format_fraction(Fraction(4, 1)), "4")
        self.assertEqual(carillon.format_fraction(Fraction(1, 2)), "0.50")


class CliTests(unittest.TestCase):
    def test_change_expands_inline_notation(self):
        code, out, _ = run(["change", "4", "x"])
        self.assertEqual(code, carillon.EXIT_OK)
        self.assertEqual(out.split(), ["start", "1234", "x", "2143"])

    def test_bad_input_exits_2_with_location(self):
        path = write_method("stage = 4\nlead = x\nstage = 5\n")
        try:
            code, _, err = run(["summary", path])
        finally:
            os.unlink(path)
        self.assertEqual(code, carillon.EXIT_INPUT_ERROR)
        self.assertIn(":3: error:", err)

    def test_true_example_check_exits_0(self):
        code, out, _ = run(["check", EXAMPLE])
        self.assertEqual(code, carillon.EXIT_OK)
        self.assertIn("TRUE", out)

    def test_documented_commands_run_on_the_example(self):
        for argv in (
            ["summary", EXAMPLE],
            ["summary", EXAMPLE, "--json"],
            ["explain", EXAMPLE],
            ["rows", EXAMPLE],
            ["path", EXAMPLE, "1"],
            ["time", EXAMPLE, "--changes", "5000", "--per-change", "2.5"],
        ):
            with self.subTest(argv=argv):
                code, out, _ = run(argv)
                self.assertEqual(code, carillon.EXIT_OK)
                self.assertTrue(out.strip())

    def test_time_uses_course_length(self):
        code, out, _ = run(["time", EXAMPLE, "--changes", "80", "--per-change", "3"])
        self.assertEqual(code, carillon.EXIT_OK)
        tokens = out.split()
        self.assertIn("10", tokens)
        self.assertIn("(8", tokens)
        self.assertIn("4:00", tokens)

    def test_path_rejects_bell_outside_stage(self):
        code, _, err = run(["path", EXAMPLE, "9"])
        self.assertEqual(code, carillon.EXIT_INPUT_ERROR)
        self.assertIn("bell must be between 1 and 4", err)


if __name__ == "__main__":
    unittest.main()
