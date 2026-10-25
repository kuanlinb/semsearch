# Translations

The interface follows your Mac's language. Each file here translates it into one language:

| File | Language |
|---|---|
| `zh-Hant.json` | 繁體中文 |
| `zh-Hans.json` | 简体中文 |
| `ja.json` | 日本語 |
| `ko.json` | 한국어 |

Any other language shows English.

## Add a language

1. Copy `ja.json` to `<code>.json`, where `<code>` is the language code macOS uses
   (`fr`, `de`, `es`, `pt`, …).
2. Translate the values. Keep the English keys as they are, and keep every `{placeholder}`
   such as `{n}` or `{names}`.
3. Run `python -m pytest tests/test_l10n.py` to check that nothing is missing, then open a pull request.

Translations by native speakers are very welcome, including fixes to the existing ones.

[← Back to README](../README.md)
