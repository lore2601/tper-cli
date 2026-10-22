from __future__ import annotations

from tper_cli import search


def test_normalize_strips_accents_case_and_punctuation() -> None:
    assert search.normalize("  Sant'Agata, Bolognese! ") == "sant agata bolognese"
    assert search.normalize("PIAZZA MEDAGLIE D`ORO") == "piazza medaglie d oro"
    assert search.normalize("Città") == "citta"


def test_score_orders_exact_prefix_tokens_substring() -> None:
    q = "stazione"
    exact = search.score(q, "stazione")
    prefix = search.score(q, "stazione centrale")
    token = search.score(q, "bologna stazione")
    assert exact > prefix > token > 0
    assert search.score("zzz", "stazione") == 0


def test_score_tolerates_a_typo() -> None:
    assert search.score("lapidri", "lapidari") > 0
    assert search.score("xxxxxxx", "lapidari") == 0


def test_rank_returns_best_first_and_limits() -> None:
    names = ["Bologna", "Bologna Centrale", "Ferrara", "San Lazzaro"]
    ranked = search.rank("bologna", names, lambda n: (n,), limit=2)
    assert [n for _, n in ranked] == ["Bologna", "Bologna Centrale"]


def test_rank_uses_any_key() -> None:
    items = [("A", "via roma"), ("B", "via milano")]
    ranked = search.rank("milano", items, lambda i: (i[0], i[1]))
    assert ranked[0][1][0] == "B"
