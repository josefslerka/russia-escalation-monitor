"""Checks for the failure modes that would corrupt a public forecast archive."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import build_site
import publish_update


class PublicationChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name) / "russia-escalation"
        shutil.copytree(build_site.DATA, self.data)
        self.state = json.loads((self.data / "state.json").read_text())

    def save_state(self):
        (self.data / "state.json").write_text(json.dumps(self.state))

    def test_probability_outside_its_range_is_rejected(self):
        hypothesis = next(iter(self.state["hypotheses"].values()))
        hypothesis["p"] = 1.1
        self.save_state()
        with patch.object(build_site, "DATA", self.data), self.assertRaisesRegex(ValueError, "probability"):
            build_site.validate()

    def test_duplicate_evidence_is_rejected(self):
        path = self.data / "evidence.jsonl"
        with path.open("a") as stream:
            stream.write(path.read_text().splitlines()[0] + "\n")
        with patch.object(build_site, "DATA", self.data), self.assertRaisesRegex(ValueError, "Duplicate"):
            build_site.validate()

    def test_mismatched_state_and_report_are_rejected(self):
        self.state["last_report"] = "reports/2026-08-28-2307.md"
        self.save_state()
        with patch.object(build_site, "DATA", self.data), self.assertRaisesRegex(ValueError, "disagree"):
            build_site.validate()

    def test_snapshot_cannot_silently_change(self):
        with patch.object(publish_update, "DATA", self.data):
            publish_update.snapshot(self.state)
            changed = copy.deepcopy(self.state)
            changed["overall_level"] = "RED"
            with self.assertRaisesRegex(ValueError, "different snapshot"):
                publish_update.snapshot(changed)

    def test_source_markup_cannot_execute_html(self):
        html, _ = build_site.render_markdown('<script>alert(1)</script>\n\n[x](javascript:alert(1))', set())
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)

    def test_historical_report_link_is_portable(self):
        name = "2026-09-27-2146.md"
        markdown = build_site.public_text(f"[prior](<{build_site.ROOT}/russia-escalation/reports/{name}>)")
        html, _ = build_site.render_markdown(markdown, {name})
        self.assertIn('href="../reports/2026-09-27-2146.html"', html)
        self.assertNotIn("/Users/", html)


if __name__ == "__main__":
    unittest.main()
