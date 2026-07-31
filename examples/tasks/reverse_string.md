# Reverse-a-string function with tests

## Objective
Write a Python function that reverses a string, and add unit tests for it.

## Requirements
- Function signature: `reverse(s: str) -> str`.
- Pure function: no side effects, no I/O.
- Handles the empty string and single-character strings.
- Correctly handles non-ASCII / multi-byte characters (reverse by Unicode code
  point, not by byte).

## Acceptance criteria
| Input | Output |
|-------|--------|
| `"abc"` | `"cba"` |
| `""` | `""` |
| `"a"` | `"a"` |
| `"résumé"` | `"émusér"` |

## Plan
1. Implement `reverse` in a small module.
2. Add unit tests covering each acceptance row above.
3. Run the tests and report pass/fail.
