"""Tests for the contribution snake. Run with:  python -m unittest discover -s snake -v"""

import random
import unittest
import xml.etree.ElementTree as ET

import snake_game as sg


def random_graph(rng: random.Random, weeks: int, density: float) -> sg.Graph:
    """A made-up contribution graph. Like the real one, its first week can start
    on any weekday and its last week can stop on any."""
    first, last = rng.randrange(7), rng.randrange(7)
    levels = {}
    for column in range(weeks):
        for weekday in range(7):
            if (column == 0 and weekday < first) or (column == weeks - 1 and weekday > last):
                continue
            levels[(weekday + 1, column)] = rng.randint(1, 4) if rng.random() < density else 0
    return sg.Graph(weeks, levels)


class LoopTests(unittest.TestCase):
    def test_visits_every_cell_once_and_comes_back(self):
        for columns in (2, 4, 52, 54):
            loop = sg.hamiltonian_cycle(columns)
            self.assertEqual(len(loop), sg.ROWS * columns)
            self.assertEqual(len(set(loop)), len(loop))
            for a, b in zip(loop, loop[1:] + loop[:1]):
                self.assertEqual(abs(a[0] - b[0]) + abs(a[1] - b[1]), 1, (a, b))

    def test_odd_numbers_of_weeks_get_a_spare_column(self):
        self.assertEqual(sg.board_columns(53), 54)
        self.assertEqual(sg.board_columns(52), 52)
        self.assertEqual(sg.board_columns(1), 4)  # room for the starting snake in the lane


class GameTests(unittest.TestCase):
    def test_never_crashes_and_eats_everything(self):
        """From an empty graph to one where every day has contributions."""
        rng = random.Random(1303)
        games = 0
        for weeks in (1, 2, 52, 53, 54):
            for density in (0, 0.02, 0.1, 0.3, 0.6, 0.9, 1):
                for _ in range(4):
                    graph = random_graph(rng, weeks, density)
                    game = sg.Planner(sg.board_columns(weeks)).play(graph.food)
                    sg.check(game, graph.food)  # raises if any rule of Snake is broken
                    self.assertEqual(game.length_after(game.moves), sg.START_LENGTH + len(graph.food))
                    games += 1
        self.assertEqual(games, 140)

    def test_shortcuts_take_the_shortest_route(self):
        """One square near the far end: following the loop would take over 300
        moves, but the shortest route from the start is 4 down and 50 across."""
        planner = sg.Planner(54)
        game = planner.play({(4, 50)})
        self.assertGreater(planner.ahead(game.path[sg.START_LENGTH - 1], (4, 50)), 300)
        self.assertEqual(game.moves, 54)

    def test_check_catches_a_crash(self):
        game = sg.Planner(4).play({(1, 0)})
        bad = sg.Game(game.columns, game.start_length, game.path + [game.path[-2]], game.eaten)
        with self.assertRaises(RuntimeError):
            sg.check(bad, {(1, 0)})

    def test_svgs_are_well_formed(self):
        graph = random_graph(random.Random(7), 53, 0.2)
        game = sg.Planner(sg.board_columns(53)).play(graph.food)
        for theme in sg.THEMES.values():
            ET.fromstring(sg.render(graph, game, theme, sg.move_time(game.moves)))


if __name__ == "__main__":
    unittest.main()
