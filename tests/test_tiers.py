"""Result tiers from reranker scores: best matches, less related, and hidden."""
from semsearch import search


def _r(rel, match="name", exact=False):
    return {"match": match, "rel": rel, "exact": exact}


def test_tiers_by_gap_from_the_top():
    out = search._tiers([_r(3.0), _r(1.5), _r(-1.0), _r(-4.5), _r(None)])
    # top 3.0: first tier from 1.0, shown from -2.0
    assert [(r["rel"], r["tier"]) for r in out] == [(3.0, 1), (1.5, 1), (-1.0, 2)]


def test_low_but_clear_winner_is_still_first():
    # an indirect match can score low; what matters is the gap to the rest
    out = search._tiers([_r(-6.7), _r(-8.7), _r(-10.9), _r(-11.0)])
    assert [(r["rel"], r["tier"]) for r in out] == [(-6.7, 1), (-8.7, 1)]


def test_places_and_exact_names_stay_first():
    out = search._tiers([_r(4.0), _r(-6.0, exact=True), _r(None, match="place"), _r(1.0)])
    assert [r["tier"] for r in out] == [1, 1, 1, 2]


def test_no_scores_means_no_tiers():
    rows = [_r(None), _r(None)]
    assert search._tiers(rows) == rows


def test_a_place_outranks_weak_files():
    # "trash": the Trash itself is the answer; weak file matches drop out
    out = search._tiers([_r(None, match="place"), _r(-8.0), _r(-9.1)])
    assert [(r["match"], r["tier"]) for r in out] == [("place", 1)]
