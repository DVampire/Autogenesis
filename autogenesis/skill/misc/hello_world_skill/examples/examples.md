---
type: examples
---

# hello_world_skill — scripts/hello.py Usage Examples

## Generate a greeting (default casual style)

```bash
python scripts/hello.py --name "Alice"
# Hey there, Alice! 👋 Welcome aboard!
```

## Generate a formal greeting

```bash
python scripts/hello.py --name "Professor Zhang" --style formal
# Good day, Professor Zhang. It is a pleasure to make your acquaintance.
```

## Generate a festive greeting

```bash
python scripts/hello.py --name "Bob" --style festive
# 🎉 Happy celebrations, Bob! Wishing you all the best! 🎉
```

## Generate a locale-based greeting

```bash
python scripts/hello.py --name "Alice" --locale zh
# 你好，Alice！

python scripts/hello.py --name "Alice" --locale ja
# こんにちは、Alice！
```

## Validate a greeting

```bash
python scripts/hello.py --validate --input "Hey there, Alice!"
# Validation passed.
# exit code: 0

python scripts/hello.py --validate --input ""
# Validation failed: greeting is empty.
# exit code: 1
```

## List available styles

```bash
python scripts/hello.py --list-styles
# casual     — Hey there, <name>! 👋 Welcome aboard!
# formal     — Good day, <name>. It is a pleasure to make your acquaintance.
# festive    — 🎉 Happy celebrations, <name>! Wishing you all the best! 🎉
```

## List available locales

```bash
python scripts/hello.py --list-locales
# en    — Hello, <name>!
# zh    — 你好，<name>！
# ja    — こんにちは、<name>！
```
