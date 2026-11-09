import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from analyze import changes, ts  # noqa: E402
from doc_profile import auc  # noqa: E402
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
        opened = {"o/a#1": ts(t.format(3)), "o/b#2": ts(t.format(4)), "o/c#3": ts(t.format(5)),
                  "o/d#4": ts(t.format(5)), "o/e#5": ts(t.format(5))}
        ch = sorted(changes(cases, ("branch", "pr-link", "issue-strong"), 12, opened),
                    key=lambda c: c["prs"])
        self.assertEqual([c["targets"] for c in ch], [["o/a", "o/b", "o/c"], ["o/d", "o/e"]])
        self.assertEqual(ch[0]["pre_work_issue"], "o/a#9")
        self.assertIsNone(ch[1]["pre_work_issue"])
        self.assertEqual((ch[0]["opened_spread_s"], ch[1]["opened_spread_s"]), (172800.0, 0.0))


if __name__ == "__main__":
    unittest.main()
