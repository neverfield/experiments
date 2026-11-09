import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
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


if __name__ == "__main__":
    unittest.main()
