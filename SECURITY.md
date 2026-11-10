# Security

## Reporting a problem

Please report security problems privately, not in a public issue: open the
[Security tab](https://github.com/kuanlinb/semsearch/security) and click **Report a vulnerability**.
Include what an attacker could do and the steps to reproduce it. You should get a reply within a week.

Only the latest version on `main` is supported.

## What SemSearch exposes

- **Your files stay on your Mac.** Indexing and search run locally; the only download is the
  embedding model from Hugging Face. Nothing is sent anywhere unless you set up the optional
  [remote reranker](remote/README.md), which receives the query and short snippets of the top results.
- **A local search service** listens on `127.0.0.1:8799` (8800, 8801… for other accounts), so other computers
  cannot reach it. Requests that a web page on another site makes the browser send to it are refused
  (`Sec-Fetch-Site` / `Origin`), so such a page cannot run searches or measure how long they take.
  Web pages in your browser cannot read it either: it only answers requests addressed to
  `127.0.0.1` or `localhost`, sends no CORS headers, and changes (like re-indexing) need a
  custom header that pages cannot send.
- **Other programs running on the same Mac can query it**, including ones macOS has not given
  access to your Documents, Desktop or Downloads, and other user accounts on the Mac. They would
  see file names, paths and short snippets. Keep this in mind on a shared Mac.
- **The index files are private to your account.** `~/.semsearch` (which holds the text read
  from your documents) is created readable by you only (since 0.1.6; older installs are fixed on
  the next start). Programs running as you can still read it, as they can read the documents.
- **Programs running as you could borrow SemSearch's folder access.** The search service runs
  Python code from the folder SemSearch was installed from, and macOS counts what it reads as
  SemSearch's. A program that can change those files could therefore read Documents, Desktop and
  Downloads through it. Install from a folder only you can write to (the default).
- **The app is not notarized.** `./install.sh` signs it with a self-signed certificate created on your
  Mac, in its own keychain (`semsearch-signing`), only so that folder permissions survive updates. Build it from source;
  do not run a copy someone sends you.
