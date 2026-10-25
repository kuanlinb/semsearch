# Contributing

Contributions are welcome, small ones included. Some places to start:

- **Translate the interface** into your language, or fix an existing translation: see
  [l10n/README.md](l10n/README.md). Native speakers are especially welcome.
- **Describe more apps.** `semsearch/apps.py` has a short line for common apps ("take notes,
  notebooks") so people can find an app by what it does. Add the apps you use.
- **Report searches that go wrong.** Open an issue with what you typed, what you expected and what
  came first. Make up an example if the real one is private.
- **Improve the docs**, if something was unclear when you installed or used SemSearch.

Bug fixes and new features are welcome too. If you're planning a bigger change, opening an issue
first helps us agree on the approach before you put in the work.

## Development

```bash
git clone https://github.com/kuanlinb/semsearch.git
cd semsearch
SEMSEARCH_APP=/tmp/SemSearch.app SEMSEARCH_SKIP_AGENT=1 ./install.sh   # builds everything, installs nothing
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests      # a tiny fake model, no download
```

More in [docs/troubleshooting.md](docs/troubleshooting.md#development). Please keep pull requests
focused on one change, and add a test when you change how search or indexing behaves.

Security problems: please follow [SECURITY.md](SECURITY.md) instead of opening an issue.
