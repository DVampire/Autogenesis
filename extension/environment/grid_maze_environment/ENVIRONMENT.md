---
name: grid_maze_environment
description: Grid maze loaded from an Excel map.
version: 1.2.0
type: worker
---

<environment_grid_maze_environment>

## State
Maintains the grid loaded from an Excel map, the current position (`pos`), the previous move direction (`came_from`), and the number of turns taken (`turn`). The grid is a 20x9 map where `START` is A1 and `END` is I20. Includes `legal_moves` (available directions excluding came_from) and `stuck` in `get_state`.

## Actions

### load_map
Load grid maze from an Excel map. Args: `path` (str). Reads the map colors and START/END positions.

### reset
Reset the environment to the START cell.

### move
Move up, down, left, or right. Args: `direction` (str). A turn is two single steps along the corridor, and the direction may change between them.

### undo
Take back the last step, restoring position and came-from.
