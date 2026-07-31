# Hello World Skill — API Reference

## HelloGreeter Class

### Constructor

```python
HelloGreeter(
    default_name: str = None,     # fallback target name
    default_style: str = None,    # fallback greeting style
    default_locale: str = None,   # fallback locale code
    resource_path: Path = None,   # custom path to greetings.json
)
```

All parameters are optional. When omitted, values are resolved in this order:
1. Environment variable (`HELLO_DEFAULT_NAME`, `HELLO_DEFAULT_STYLE`, `HELLO_LOCALE`)
2. `resources/greetings.json` → `defaults` field
3. Hard-coded fallback (`"World"`, `"casual"`, `"en"`)

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `generate` | `(name?, style?) → str` | Generate a greeting using a style template |
| `generate_locale` | `(name?, locale?) → str` | Generate a simple locale-based greeting |
| `validate` | `(text) → bool` | Check greeting is non-empty and within length limit |
| `list_styles` | `() → None` | Print all available styles with preview |
| `list_locales` | `() → None` | Print all available locales with preview |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `available_styles` | `List[str]` | Names of all registered styles |
| `available_locales` | `List[str]` | Codes of all registered locales |

---

## Resource File Schema

`resources/greetings.json` structure:

```json
{
  "styles": {
    "<style_name>": {
      "templates": ["template with {name} placeholder", ...]
    }
  },
  "locales": {
    "<locale_code>": "template with {name} placeholder"
  },
  "defaults": {
    "name": "World",
    "style": "casual",
    "locale": "en"
  }
}
```

### Rules

- Every template **must** contain a `{name}` placeholder
- `styles.<style>.templates` is a list; the script randomly picks one per call
- `locales.<code>` is a single string (one template per locale)
- `defaults` values are used when no argument or env var is provided

### Adding a Custom Style

Add a new key under `styles`:

```json
{
  "styles": {
    "pirate": {
      "templates": [
        "Ahoy, {name}! Welcome aboard, matey! 🏴‍☠️",
        "Yarr, {name}! Set sail for adventure! ⚓"
      ]
    }
  }
}
```

No code changes needed — `HelloGreeter` picks it up automatically.

### Adding a Custom Locale

Add a new key under `locales`:

```json
{
  "locales": {
    "ko": "안녕하세요, {name}!"
  }
}
```

---

## CLI Reference

```
usage: hello.py [-h] [--name NAME] [--style STYLE] [--locale LOCALE]
                [--validate] [--input INPUT] [--list-styles] [--list-locales]
```

| Flag | Description | Example |
|------|-------------|---------|
| `--name` | Target name | `--name "Alice"` |
| `--style` | Greeting style | `--style formal` |
| `--locale` | Locale code | `--locale zh` |
| `--validate` | Validate mode | `--validate --input "text"` |
| `--input` | Text to validate | used with `--validate` |
| `--list-styles` | Print styles | `--list-styles` |
| `--list-locales` | Print locales | `--list-locales` |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success / validation passed |
| `1` | Validation failed |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HELLO_DEFAULT_NAME` | `World` | Fallback name when `--name` is omitted |
| `HELLO_DEFAULT_STYLE` | `casual` | Fallback style when `--style` is omitted |
| `HELLO_LOCALE` | `en` | Fallback locale when `--locale` is omitted |

---

## Validation Rules

| Rule | Condition | Error Message |
|------|-----------|---------------|
| Non-empty | `text.strip()` is truthy | "greeting is empty" |
| Length limit | `len(text) <= 500` | "greeting exceeds 500 characters" |
