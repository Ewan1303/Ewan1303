#!/usr/bin/env python3
"""Play Snake on a GitHub contribution graph and save it as animated SVGs.

The board is the contribution graph (a row per weekday, a column per week)
with a lane along the top. Every square with contributions is food. The snake
eats them all, growing one segment per square as in the arcade game, and it
never runs into itself:

1. A Hamiltonian cycle covers the board: a loop that visits every cell exactly
   once and comes back to the start. Following it, the snake's body always
   trails behind its head.
2. Following the loop everywhere would be slow, so the snake takes shortcuts.
   On each move it steps to the neighbouring cell that gets it furthest along
   the loop without going past the next square of food.
3. That keeps it safe however long it grows. It only ever moves forward along
   the loop and never skips a square, so every square left is somewhere
   between its head and its tail along the loop. It reaches each one before it
   could reach its own body, and the game ends with the last square.

Uses only the standard library, so it runs on a bare GitHub Actions runner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path

Cell = tuple[int, int]  # (row, column) on the board

ROWS = 8  # row 0 is the lane above the graph; rows 1 to 7 are Sunday to Saturday
START_LENGTH = 4
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
QUERY = """
query ($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""


# The graph -------------------------------------------------------------------

@dataclass
class Graph:
    weeks: int
    levels: dict[Cell, int]  # one cell per day: its contribution level, 0 to 4

    @property
    def food(self) -> set[Cell]:
        return {cell for cell, level in self.levels.items() if level}


def fetch_calendar(user: str, token: str) -> dict:
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "contribution-snake"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if data.get("errors"):
        raise SystemExit(f"GitHub API error: {data['errors']}")
    return data


def parse_calendar(data: dict) -> Graph:
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    levels = {(day["weekday"] + 1, column): LEVELS[day["contributionLevel"]]
              for column, week in enumerate(weeks) for day in week["contributionDays"]}
    return Graph(len(weeks), levels)


# The board and its loop ------------------------------------------------------

def board_columns(weeks: int) -> int:
    """One column per week, plus a spare one when needed, because the loop
    needs an even number of columns. At least START_LENGTH columns, so the
    starting snake fits in the lane."""
    return max(START_LENGTH + START_LENGTH % 2, weeks + weeks % 2)


def hamiltonian_cycle(columns: int) -> list[Cell]:
    """Every cell of the board once, each next to the one before, ending next to
    the start: down column 0, then up and down columns 1, 2, ... through the
    graph's rows, then back left along the lane."""
    if columns < 2 or columns % 2:
        raise ValueError("the loop needs an even number of columns")
    loop = [(row, 0) for row in range(ROWS)]
    for column in range(1, columns):
        rows = range(ROWS - 1, 0, -1) if column % 2 else range(1, ROWS)
        loop += [(row, column) for row in rows]
    loop += [(0, column) for column in range(columns - 1, 0, -1)]
    return loop


# Playing ---------------------------------------------------------------------

@dataclass
class Game:
    columns: int
    start_length: int
    path: list[Cell]        # the starting body from tail to head, then the head after each move
    eaten: dict[Cell, int]  # square -> the move that ate it (the first move is 1)

    @property
    def moves(self) -> int:
        return len(self.path) - self.start_length

    def length_after(self, move: int) -> int:
        return self.start_length + sum(1 for m in self.eaten.values() if m <= move)


def step(body: deque, cells: set, growth: int, food: set, head: Cell) -> int | None:
    """Move the head to `head`, eating the food there if there is any. Changes
    `body`, `cells` and `food` in place and returns the growth still to come,
    or None if the snake ran into itself."""
    if head in food:
        food.discard(head)
        growth += 1
    if growth:
        growth -= 1  # growing: the tail stays where it is for this move
    else:
        cells.discard(body.popleft())
    if head in cells:
        return None
    body.append(head)
    cells.add(head)
    return growth


class Planner:
    def __init__(self, columns: int):
        self.columns = columns
        self.loop = hamiltonian_cycle(columns)
        self.size = len(self.loop)
        self.position = {cell: i for i, cell in enumerate(self.loop)}
        self.after = {cell: self.loop[(i + 1) % self.size] for i, cell in enumerate(self.loop)}

    def ahead(self, a: Cell, b: Cell) -> int:
        """How many cells along the loop b is from a."""
        return (self.position[b] - self.position[a]) % self.size

    def neighbours(self, cell: Cell) -> list[Cell]:
        row, column = cell
        return [n for n in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
                if n in self.position]

    def play(self, food: set[Cell], start_length: int = START_LENGTH) -> Game:
        """Eat every square, starting in the lane at the top left."""
        body = deque(self.loop[self.size - start_length + 1:] + self.loop[:1])
        cells, food, growth = set(body), set(food), 0
        if cells & food or not food <= self.position.keys():
            raise ValueError("food must be on the board and clear of the starting snake")
        path, eaten = list(body), {}
        # The head never passes a square, so it eats them in the order they
        # come along the loop.
        queue = deque(sorted(food, key=lambda square: self.ahead(body[-1], square)))
        while queue:
            head, target = body[-1], queue[0]
            reach = self.ahead(head, target)
            # The next cell on the loop is always a candidate (it is 1 ahead),
            # so there is always a move.
            move = max((n for n in self.neighbours(head) if self.ahead(head, n) <= reach),
                       key=lambda n: self.ahead(head, n))
            if move == target:
                queue.popleft()
                eaten[move] = len(path) - start_length + 1
            growth = step(body, cells, growth, food, move)
            if growth is None:  # can't happen: see point 3 at the top of this file
                raise AssertionError(f"the snake ran into itself at {move}")
            path.append(move)
        if not eaten:  # nothing to eat: take a short stroll along the loop instead
            for _ in range(2 * ROWS):
                step(body, cells, 0, food, self.after[body[-1]])
                path.append(body[-1])
        return Game(self.columns, start_length, path, eaten)


def check(game: Game, food: set[Cell]) -> None:
    """Replay a game from scratch and raise if it breaks the rules of Snake:
    one cell per move, never off the board, never into itself, every square
    eaten."""
    body = deque(game.path[:game.start_length])
    cells, food, growth = set(body), set(food), 0
    if len(cells) != game.start_length:
        raise RuntimeError("the snake starts tangled up")
    for move, head in enumerate(game.path[game.start_length:], 1):
        (row, column), (last_row, last_column) = head, body[-1]
        if abs(row - last_row) + abs(column - last_column) != 1:
            raise RuntimeError(f"move {move} jumps from {body[-1]} to {head}")
        if not (0 <= row < ROWS and 0 <= column < game.columns):
            raise RuntimeError(f"move {move} leaves the board")
        if (head in food) != (game.eaten.get(head) == move):
            raise RuntimeError(f"move {move}: what was eaten doesn't match")
        growth = step(body, cells, growth, food, head)
        if growth is None:
            raise RuntimeError(f"move {move} runs into the snake's own body")
    if food:
        raise RuntimeError(f"{len(food)} squares were left uneaten")


# Drawing ---------------------------------------------------------------------

PITCH, SQUARE = 16, 12  # pixels between cell centres, and the size of a square
THEMES = {
    "light": {"empty": "#ebedf0", "levels": ("#9be9a8", "#40c463", "#30a14e", "#216e39"),
              "body": "#8957e5", "head": "#6639ba", "eye": "#ffffff"},
    "dark": {"empty": "#161b22", "levels": ("#0e4429", "#006d32", "#26a641", "#39d353"),
             "body": "#a371f7", "head": "#d2a8ff", "eye": "#0d1117"},
}
PAUSE_START, PAUSE_END, FADE = 0.6, 2.5, 0.4  # seconds


def move_time(moves: int) -> float:
    """Seconds per move: aims for about 30 seconds of play, at 8 to 20 moves a
    second."""
    return min(0.125, max(0.05, 30 / max(moves, 1)))


def centre(cell: Cell) -> tuple[float, float]:
    row, column = cell
    return column * PITCH + PITCH / 2, row * PITCH + PITCH / 2


def corners(path: list[Cell]) -> list[Cell]:
    """The path without the cells in the middle of straight runs."""
    kept = [path[0]]
    for before, cell, after in zip(path, path[1:], path[2:]):
        if (cell[0] - before[0], cell[1] - before[1]) != (after[0] - cell[0], after[1] - cell[1]):
            kept.append(cell)
    kept.append(path[-1])
    return kept


def render(graph: Graph, game: Game, theme: dict, seconds_per_move: float) -> str:
    """An SVG of the game, animated with SMIL so it plays inside an <img>.

    The body is one thick line along the head's whole route, with a dash
    pattern that shows only the stretch between the tail and the head. The head
    moves at a steady speed. During each move that eats, the body grows by one
    cell, so the tail stays still for that move."""
    start = PAUSE_START
    finish = start + game.moves * seconds_per_move
    duration = finish + PAUSE_END + FADE
    route = "M" + " L".join(f"{x:g} {y:g}" for x, y in map(centre, corners(game.path)))
    route_length = PITCH * (len(game.path) - 1)
    gap = route_length + 4 * PITCH  # longer than the route, so the dash pattern never repeats

    marks = {0.0, start, finish, duration}
    for move in game.eaten.values():
        marks |= {start + (move - 1) * seconds_per_move, start + move * seconds_per_move}
    times, heads, bodies = [], [], []
    for t in sorted(marks):
        done = 0 if t <= start else game.moves if t >= finish else round((t - start) / seconds_per_move)
        times.append(t / duration)
        heads.append(PITCH * (game.start_length - 1 + done))
        bodies.append(PITCH * (game.length_after(done) - 1))
    times[0], times[-1] = 0.0, 1.0

    timing = f'dur="{duration:.2f}s" repeatCount="indefinite"'
    key_times = ";".join(f"{t:.5f}" for t in times)
    dash_arrays = ";".join(f"{b:g} {gap:g}" for b in bodies)
    dash_offsets = ";".join(f"{b - h:g}" for b, h in zip(bodies, heads))
    key_points = ";".join(f"{h / route_length:.5f}" for h in heads)
    fade_times = f"0;{0.3 / duration:.5f};{(duration - FADE) / duration:.5f};1"

    width, height = game.columns * PITCH, ROWS * PITCH
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {width + 8} {height + 8}" '
             f'width="{width + 8}" height="{height + 8}">']
    inset = (PITCH - SQUARE) / 2
    for (row, column), level in sorted(graph.levels.items(), key=lambda item: (item[0][1], item[0][0])):
        colour = theme["levels"][level - 1] if level else theme["empty"]
        square = (f'<rect x="{column * PITCH + inset:g}" y="{row * PITCH + inset:g}" '
                  f'width="{SQUARE}" height="{SQUARE}" rx="2" fill="{colour}"')
        move = game.eaten.get((row, column))
        if move is None:
            parts.append(square + "/>")
        else:  # the square empties as the head arrives on it
            gone = (start + (move - 0.4) * seconds_per_move) / duration
            parts.append(f'{square}><animate attributeName="fill" values="{colour};{theme["empty"]}" '
                         f'keyTimes="0;{gone:.5f}" calcMode="discrete" {timing}/></rect>')
    parts.append(f'<g><animate attributeName="opacity" values="0;1;1;0" keyTimes="{fade_times}" {timing}/>')
    parts.append(
        f'<path d="{route}" fill="none" stroke="{theme["body"]}" stroke-width="10" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'stroke-dasharray="{bodies[0]:g} {gap:g}" stroke-dashoffset="{bodies[0] - heads[0]:g}">'
        f'<animate attributeName="stroke-dasharray" values="{dash_arrays}" keyTimes="{key_times}" {timing}/>'
        f'<animate attributeName="stroke-dashoffset" values="{dash_offsets}" keyTimes="{key_times}" {timing}/>'
        f'</path>')
    parts.append(
        f'<g><animateMotion path="{route}" keyPoints="{key_points}" keyTimes="{key_times}" '
        f'calcMode="linear" rotate="auto" {timing}/>'
        f'<circle r="6.5" fill="{theme["head"]}"/>'
        f'<circle cx="2.2" cy="-2.6" r="1.5" fill="{theme["eye"]}"/>'
        f'<circle cx="2.2" cy="2.6" r="1.5" fill="{theme["eye"]}"/></g>')
    parts.append("</g></svg>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Play Snake on a GitHub contribution graph.")
    parser.add_argument("--user", required=True, help="GitHub username")
    parser.add_argument("--out", type=Path, default=Path("dist"), help="folder to write the SVGs to")
    parser.add_argument("--calendar", type=Path, help="a saved GraphQL response to use instead of fetching")
    args = parser.parse_args(argv)
    if args.calendar:
        data = json.loads(args.calendar.read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            sys.exit("Set GITHUB_TOKEN to fetch the contribution graph.")
        data = fetch_calendar(args.user, token)
    graph = parse_calendar(data)
    game = Planner(board_columns(graph.weeks)).play(graph.food)
    check(game, graph.food)
    seconds = move_time(game.moves)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, theme in (("github-snake.svg", "light"), ("github-snake-dark.svg", "dark")):
        (args.out / name).write_text(render(graph, game, THEMES[theme], seconds), encoding="utf-8")
    print(f"Ate {len(game.eaten)} squares in {game.moves} moves, growing from {game.start_length} "
          f"to {game.length_after(game.moves)} cells, at {seconds:.3f} s a move.")


if __name__ == "__main__":
    main()
