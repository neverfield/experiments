import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.refs import extract_keys, extract_refs, is_bot, is_generic_branch  # noqa: E402


class RefsTest(unittest.TestCase):
    def test_url_short_and_local_forms(self):
        text = (
            "Depends on https://github.com/elastic/kibana/pull/123 and elastic/beats#45.\n"
            "Fixes #9"
        )
        refs = extract_refs(text, "elastic/elasticsearch")
        got = {(r.target, r.form, r.context, r.closes, r.kind) for r in refs}
        self.assertIn(("elastic/kibana#123", "url", "depends", False, "pull"), got)
        self.assertIn(("elastic/beats#45", "short", "depends", False, "any"), got)
        self.assertIn(("elastic/elasticsearch#9", "local", "mention", True, "any"), got)
        self.assertEqual(len(refs), 3)

    def test_url_not_double_counted_as_short(self):
        refs = extract_refs("see https://github.com/grafana/loki/issues/7", "grafana/grafana")
        self.assertEqual([r.target for r in refs], ["grafana/loki#7"])
        self.assertEqual(refs[0].context, "relates")

    def test_template_comments_code_and_quotes_dropped(self):
        text = "<!-- e.g. Fixes org/repo#1 -->\n```\nfoo/bar#2\n```\n> quoted a/b#3\nreal c/d#4"
        self.assertEqual([r.target for r in extract_refs(text, "x/y")], ["c/d#4"])

    def test_closing_cross_repo(self):
        refs = extract_refs("Closes hashicorp/terraform#88", "hashicorp/terraform-plugin-go")
        self.assertTrue(refs[0].closes)

    def test_backport_and_companion(self):
        r1 = extract_refs("Backport of grafana/grafana#100 to v11", "grafana/grafana")[0]
        self.assertEqual(r1.context, "port")
        r2 = extract_refs("Companion PR: grafana/grafana-plugin-sdk-go#5", "grafana/grafana")[0]
        self.assertEqual(r2.context, "companion")

    def test_html_entity_not_a_ref(self):
        self.assertEqual(extract_refs("a &#123; b", "x/y"), [])

    def test_keys(self):
        self.assertEqual(
            extract_keys("[FLINK-1234][connectors] fix, see CVE-2024-1 and UTF-8 and KEP-4381"),
            ["FLINK-1234", "KEP-4381"],
        )
        self.assertEqual(extract_keys("OCPBUGS-77: x <!-- JIRA-1 -->"), ["OCPBUGS-77"])

    def test_branches_and_bots(self):
        self.assertTrue(is_generic_branch("main"))
        self.assertTrue(is_generic_branch("dependabot/npm/foo-1.2"))
        self.assertTrue(is_generic_branch("patch-3"))
        self.assertFalse(is_generic_branch("jdoe/add-otlp-histogram-support"))
        self.assertTrue(is_bot("dependabot[bot]"))
        self.assertTrue(is_bot("whoever", "Bot"))
        self.assertFalse(is_bot("octocat", "User"))


if __name__ == "__main__":
    unittest.main()
