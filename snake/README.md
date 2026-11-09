# Contribution snake

The snake at the bottom of [my profile](https://github.com/Ewan1303) plays Snake on my contribution graph. Every square with contributions is food. The snake eats them all, grows one segment for each, and never runs into itself. It's redrawn every day, so it gets longer as the graph fills up.

## How it moves

1. **A loop through every cell.** The board is the graph plus a lane along the top. A Hamiltonian cycle covers it: a route that visits every cell exactly once and comes back to the start. It runs down the first week, up and down each week after that, and back along the lane.
2. **Shortcuts.** Following the whole loop would be slow, so on each move the snake steps to whichever neighbouring cell gets it furthest along the loop without going past the next square. That takes it more or less straight to each square.
3. **Why it can't crash.** It only ever moves forward along the loop and never skips a square, so every square left is somewhere between its head and its tail along the loop. It always reaches the next square before it could reach its own body, and the game ends with the last one. That holds however long it gets: in the tests, every day of the graph has contributions and it still finishes.

Before a game is drawn, it's replayed move by move to check that the snake moves one cell at a time, stays on the board, never hits itself and eats every square.

## Files

| File | What it does |
|---|---|
| `snake_game.py` | Fetches the graph from the GitHub GraphQL API, plans the game, checks it and writes `github-snake.svg` and `github-snake-dark.svg`. The SVGs are animated with SMIL, so they play inside an `<img>`. Standard library only. |
| `test_snake_game.py` | Checks the loop and plays 140 random graphs, from empty to every day filled. |
| [`snake.yml`](../.github/workflows/snake.yml) | Runs the tests, plays the game every day and publishes the SVGs to the `output` branch. |

To run it yourself:

```bash
python -m unittest discover -s snake -v
```

```bash
GITHUB_TOKEN=<a token> python snake/snake_game.py --user <username> --out dist
```
