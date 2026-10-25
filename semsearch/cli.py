"""Command-line search: python -m semsearch.cli the slides about attention from last semester"""
import json
import os
import sys
import urllib.parse
import urllib.request

from . import config


def main():
    q = " ".join(sys.argv[1:]).strip()
    if not q:
        print("usage: ss <what you are looking for>")
        return 1
    url = f"http://127.0.0.1:{config.load()['port']}/search?" + urllib.parse.urlencode({"q": q, "n": 15})
    try:
        r = json.load(urllib.request.urlopen(url, timeout=15))
    except OSError:
        print("Cannot reach the search service. Is the SemSearch app running?")
        return 1
    home = os.path.expanduser("~")
    for i, h in enumerate(r["results"], 1):
        tag = {"content": "content", "place": "place"}.get(h["match"], "name")
        if h.get("group"):
            tag += f", +{len(h['group'])} in the same folder"
        print(f"\033[1m{i:>2}. {h['name']}\033[0m  \033[2m[{tag}]\033[0m")
        print(f"    \033[2m{h['path'].replace(home, '~', 1)}\033[0m")
        if h["snippet"]:
            print(f"    {h['snippet'][:110]}")
        for g in h.get("group", [])[:5]:
            print(f"    \033[2m  + {g['name']}\033[0m")
    print(f"\033[2m{len(r['results'])} results · {r['ms']} ms\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
