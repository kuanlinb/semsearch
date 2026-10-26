"""Hit@1/@3 for the 76 text questions and the photo questions: summary.py <tag>…"""
import json, sys, collections
for tag in sys.argv[1:]:
    r = json.load(open(f"eval/lookalike/results/{tag}.json"))
    c = collections.defaultdict(lambda: [0, 0, 0])
    for q in r["queries"]:
        t = c[q["tag"] if q["tag"].startswith("photo") else "text"]
        t[0] += q["rank"] == 1; t[1] += bool(q["rank"] and q["rank"] <= 3); t[2] += 1
    s = r["summary"]
    print(f"{tag:22}", "  ".join(f"{k} {v[0]}/{v[1]} of {v[2]}" for k, v in c.items()),
          f"  median {s['median_ms']} ms  index {s['index_s']} s  search RSS {s['search_peak_rss_mb']} MB")
