import http.client
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from analyze import changes, same_title, sweep_like, ts  # noqa: E402
from cochange import score as cochange_score  # noqa: E402
from doc_profile import auc  # noqa: E402
from same_org.gh import read_body  # noqa: E402
from same_org.orgs import in_owners, load_census, owners_of, search_scope  # noqa: E402
from score_review import cell, wilson  # noqa: E402


class OrgsTest(unittest.TestCase):
    def test_group_and_single_owner(self):
        self.assertEqual(owners_of("k8s"), ("kubernetes", "kubernetes-sigs"))
        self.assertEqual(owners_of("Grafana"), ("grafana",))
        self.assertEqual(search_scope("k8s"), "org:kubernetes org:kubernetes-sigs")
        self.assertTrue(in_owners("Kubernetes-SIGS/kind", owners_of("k8s")))
        self.assertFalse(in_owners("kubernetes-client/go", owners_of("k8s")))

    def test_load_census_merges_owners_and_needs_every_listing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "repos").mkdir()
            (Path(d) / "repos" / "kubernetes.jsonl").write_text(
                json.dumps({"full_name": "kubernetes/Kubernetes"}) + "\n")
            with self.assertRaises(FileNotFoundError):
                load_census(d, "k8s")
            (Path(d) / "repos" / "kubernetes-sigs.jsonl").write_text(
                json.dumps({"full_name": "kubernetes-sigs/kind"}) + "\n")
            self.assertEqual(sorted(load_census(d, "k8s")),
                             ["kubernetes-sigs/kind", "kubernetes/kubernetes"])


class ScoringTest(unittest.TestCase):
    def test_auc_with_ties(self):
        self.assertEqual(auc([3, 4, 5], [1, 2]), 1.0)
        self.assertEqual(auc([1, 2], [3, 4, 5]), 0.0)
        self.assertEqual(auc([1, 1], [1, 1]), 0.5)
        self.assertEqual(auc([2, 3], [1, 2]), 0.875)
        self.assertIsNone(auc([], [1]))

    def test_wilson_and_cell(self):
        self.assertEqual(wilson(8, 8), [0.676, 1.0])
        self.assertIsNone(wilson(0, 0))
        c = cell(["same", "same", "partial", "not"])
        self.assertEqual((c["strict"], c["lenient"], c["not"]), (0.5, 0.75, 1))


class ChangesTest(unittest.TestCase):
    def test_cases_sharing_a_pr_join_and_pre_work_issue_is_found(self):
        t = "2026-06-0{}T00:00:00+00:00"
        cases = [
            {"method": "branch", "n_targets": 2, "prs": ["o/a#1", "o/b#2"],
             "first_created": t.format(3)},
            {"method": "pr-link", "n_targets": 2, "prs": ["o/b#2", "o/c#3"],
             "first_created": t.format(4)},
            {"method": "issue-strong", "n_targets": 1, "prs": ["o/a#1"], "group": "o/a#9",
             "hub": {"author_is_bot": False, "createdAt": t.format(1)}},
            {"method": "branch", "n_targets": 2, "prs": ["o/d#4", "o/e#5"],
             "first_created": t.format(5)},
        ]
        titles = {"o/a#1": "Add quota API", "o/b#2": "Read quota in client",
                  "o/c#3": "Show quota in UI", "o/d#4": "chore: bump go to 1.26",
                  "o/e#5": "chore(deps): update go to 1.26"}
        days = {"o/a#1": 3, "o/b#2": 4, "o/c#3": 5, "o/d#4": 5, "o/e#5": 5}
        meta = {k: {"opened": ts(t.format(days[k])), "title": v} for k, v in titles.items()}
        ch = sorted(changes(cases, ("branch", "pr-link", "issue-strong"), 12, meta),
                    key=lambda c: c["prs"])
        self.assertEqual([c["targets"] for c in ch], [["o/a", "o/b", "o/c"], ["o/d", "o/e"]])
        self.assertEqual(ch[0]["pre_work_issue"], "o/a#9")
        self.assertIsNone(ch[1]["pre_work_issue"])
        self.assertEqual((ch[0]["opened_spread_s"], ch[1]["opened_spread_s"]), (172800.0, 0.0))
        self.assertEqual((ch[0]["sweep_like"], ch[1]["sweep_like"]), (False, True))
        self.assertEqual((ch[0]["same_title"], ch[1]["same_title"]), (False, False))

    def test_sweep_like(self):
        self.assertFalse(sweep_like(["Fix the shader cache", "fix the shader cache"]))
        self.assertTrue(sweep_like(["Release Notes for 7.45.0 (ga)", "Changelogs for 7.45.0"]))
        self.assertTrue(sweep_like(["[templates] Update test templates to MSTest 4.3.2",
                                    "Bump MSTest"]))
        self.assertFalse(sweep_like(["Share dashboards by link", "chore: bump go"]))
        self.assertFalse(sweep_like(["Add audit log API", "Show audit log in UI"]))
        self.assertFalse(sweep_like(["chore: bump go"]))

    def test_cochange_skips_cases_sharing_the_changes_prs(self):
        t = "2026-0{}-01T00:00:00Z"
        cases = [{"n_targets": 2, "targets": ["o/a", "o/b"], "prs": ["o/a#1", "o/b#1"],
                  "first_created": t.format(6)},
                 {"n_targets": 2, "targets": ["o/a", "o/c"], "prs": ["o/a#5", "o/c#5"],
                  "first_created": t.format(7)}]
        meta = {k: {"opened": ts(t.format(8))} for k in ("o/a#5", "o/b#9", "o/c#5")}
        chs = [{"targets": ["o/a", "o/b", "o/c"], "prs": ["o/a#5", "o/b#9", "o/c#5"],
                "sweep_like": False}]
        r = cochange_score(cases, chs, meta, ts(t.format(8)))
        self.assertEqual((r["changes"], r["all_pairs_seen"], r["any_pair_seen"]), (1, 0.0, 1.0))
        self.assertAlmostEqual(r["seed_recall"], (1 / 2 + 1 / 2 + 0) / 3, places=3)

    def test_same_title(self):
        self.assertTrue(same_title(["Fix the shader cache", "fix the shader cache!"]))
        self.assertFalse(same_title(["Fix the shader cache", "Fix the shader"]))
        self.assertFalse(same_title(["Fix the shader cache"]))


class _Body:
    """A response that hands out `chunks` one read at a time; `length` is what is unread."""

    def __init__(self, chunks, length=None):
        self.chunks, self.length = list(chunks), length

    def read(self, amt):
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        if self.length is not None:
            self.length -= len(c)
        return c


class ReadBodyTest(unittest.TestCase):
    def test_whole_body_is_returned(self):
        self.assertEqual(read_body(_Body([b"ab", b"c"], length=3), 10, clock=lambda: 0), b"abc")
        self.assertEqual(read_body(_Body([b"ab", b"c"]), 10, clock=lambda: 0), b"abc")

    def test_trickling_body_hits_the_deadline(self):
        ticks = iter(range(100))
        with self.assertRaises(TimeoutError):
            read_body(_Body([b"x"] * 50), 5, clock=lambda: next(ticks))

    def test_body_cut_short_of_its_length_raises(self):
        with self.assertRaises(http.client.IncompleteRead):
            read_body(_Body([b"ab"], length=5), 10, clock=lambda: 0)


if __name__ == "__main__":
    unittest.main()
