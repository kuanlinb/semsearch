import json, sys, collections
tags = sys.argv[1:]
R = {t: json.load(open(f"eval/lookalike/results/{t}.json")) for t in tags}
key = next(k for k in ("tag", "kind") if k in R[tags[0]]["queries"][0])
kinds = list(dict.fromkeys(q[key] for q in R[tags[0]]["queries"]))
print("kind".ljust(14), *[t.ljust(20) for t in tags])
for k in kinds + ["ALL"]:
    row = []
    for t in tags:
        qs = [q for q in R[t]["queries"] if k == "ALL" or q[key] == k]
        row.append(f"{sum(q['rank']==1 for q in qs)}/{sum(bool(q['rank'] and q['rank']<=3) for q in qs)} of {len(qs)}".ljust(20))
    print(k.ljust(14), *row)
if len(tags) == 2:
    a, b = (R[t]["queries"] for t in tags)
    for x, y in zip(a, b):
        if x["rank"] != y["rank"]:
            print(f"  {x[key]:10} {str(x['rank']):>4} → {str(y['rank']):>4}  {x['q']}")
