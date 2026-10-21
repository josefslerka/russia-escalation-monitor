"""Paired-report fixtures are local test data, never public forecasts."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import bilingual
import build_site
import check_site
import publish_update


def make_fixture(root):
    """Create a clearly labelled, disposable October22 test assessment."""
    root = Path(root)
    data = root / "russia-escalation"
    (data / "reports").mkdir(parents=True)
    (data / "snapshots").mkdir()
    for name in ("state.json", "evidence.jsonl", "watchlist.json"):
        shutil.copyfile(build_site.DATA / name, data / name)
    shutil.copyfile(build_site.DATA / "reports/2026-10-21-0708.md", data / "reports/2026-10-21-0708.md")
    shutil.copytree(build_site.ROOT / "site", root / "site")
    state = json.loads((data / "state.json").read_text())
    state.update(assessment_time="2026-10-22T07:00:00+02:00", source_cutoff="2026-10-22T07:00:00+02:00",
                 last_report="reports/2026-10-22-0700.md", one_line_judgment="TEST — nejde o novou předpověď.")
    for h in state["hypotheses"].values():
        if h.get("status", "active") == "active":
            h.update(prior=h["p"], delta_pp=0, trend="flat")
    cs_confidence = {v: k for k, v in bilingual.CONFIDENCE.items()}
    for lang in ("cs", "en"):
        rows = []
        for key, h in state["hypotheses"].items():
            if h.get("status", "active") != "active":
                continue
            confidence = h["confidence"] if lang == "en" else cs_confidence[h["confidence"]]
            rows.append(f'| {key} | {h["horizon"]} | {h["prior"]*100:g} % | {h["p"]*100:g} % | 0 | {h["range"][0]*100:g}–{h["range"][1]*100:g} % | {confidence} |')
        text = f'''# {"TEST — not a new forecast" if lang == "en" else "TEST — nejde o novou předpověď"}

**{"Overall" if lang == "en" else "Celkově"}:** {state["overall_level"]}, flat
**{"One-line judgment" if lang == "en" else "Jednovětý závěr"}:** {"Test fixture only." if lang == "en" else "Pouze testovací data."}

{state["assessment_time"]}
{state["forecast_window_end"]}

## {"Probability dashboard" if lang == "en" else "Pravděpodobnosti"}

| Event | Horizon | Prior | Now | Delta | Range | Confidence |
|---|---|---:|---:|---:|---|---|
{chr(10).join(rows)}

## {"Evidence against escalation" if lang == "en" else "Podklady proti eskalaci"}

[{"Example source" if lang == "en" else "Ukázkový zdroj"}](https://example.com/source)

[Prior](2026-10-21-0708.md)

**WDPI: {state["wdpi"]["total"]}/100**, flat
'''
        path = data / state["last_report"]
        if lang == "en":
            path = bilingual.english_path(path)
        path.write_text(text, encoding="utf-8")
    (data / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return data, state


class BilingualChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.data, self.state = make_fixture(self.root)
        self.cs = self.data / self.state["last_report"]
        self.en = bilingual.english_path(self.cs)
        self.first = next(h for h in self.state["hypotheses"].values() if h.get("status", "active") == "active")

    def validate(self):
        with patch.object(build_site, "DATA", self.data):
            return build_site.validate()

    def change(self, path, old, new):
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def test_required_from_october22_without_doubling_archive(self):
        _, _, reports = self.validate()
        self.assertEqual(len(reports), 2)
        self.en.unlink()
        with self.assertRaisesRegex(ValueError, "English report required"):
            self.validate()

    def test_legacy_report_does_not_require_a_translation(self):
        self.cs.unlink()
        self.en.unlink()
        self.state.update(assessment_time="2026-10-21T07:08:07+02:00", last_report="reports/2026-10-21-0708.md")
        (self.data / "state.json").write_text(json.dumps(self.state))
        self.validate()

    def test_orphan_translation_is_rejected(self):
        self.en.rename(self.data / "reports/2026-10-22-0701.en.md")
        with self.assertRaisesRegex(ValueError, "Orphan"):
            self.validate()

    def test_mismatched_probability_is_rejected(self):
        p = self.first["p"] * 100
        self.change(self.en, f"| {p:g} % | {p:g} % |", f"| {p:g} % | {p+1:g} % |")
        with self.assertRaisesRegex(ValueError, "table numbers"):
            self.validate()

    def test_both_versions_cannot_depart_from_state(self):
        p = self.first["p"] * 100
        for path in (self.cs, self.en):
            self.change(path, f"| {p:g} % | {p:g} % |", f"| {p:g} % | {p+1:g} % |")
        with self.assertRaisesRegex(ValueError, "differs from state"):
            self.validate()

    def test_changed_source_is_rejected(self):
        self.change(self.en, "https://example.com/source", "https://example.com/different")
        with self.assertRaisesRegex(ValueError, "source links"):
            self.validate()

    def test_changed_cutoff_is_rejected(self):
        self.change(self.en, self.state["assessment_time"], "2026-10-22T07:01:00+02:00")
        with self.assertRaisesRegex(ValueError, "timestamp"):
            self.validate()

    def test_changed_horizon_is_rejected(self):
        self.change(self.en, self.state["forecast_window_end"], "2027-03-31T23:59:59+02:00")
        with self.assertRaisesRegex(ValueError, "exact assessment timestamp and horizon"):
            self.validate()

    def test_common_stale_cutoff_cannot_hide_before_correct_timestamp(self):
        for path in (self.cs, self.en):
            self.change(path, self.state["assessment_time"], "2026-10-21T07:00:00+02:00\n" + self.state["assessment_time"])
        with self.assertRaisesRegex(ValueError, "exact assessment timestamp"):
            self.validate()

    def test_decimal_comma_and_dot_are_equivalent(self):
        self.cs.write_text(self.cs.read_text().replace("0.3", "0,3"))
        self.validate()

    def test_missing_section_is_rejected(self):
        self.change(self.en, "## Evidence against escalation", "Evidence against escalation")
        with self.assertRaisesRegex(ValueError, "section structure"):
            self.validate()

    def test_changed_confidence_is_rejected(self):
        confidence = self.first["confidence"]
        self.change(self.en, f"| {confidence} |", "| high |" if confidence != "high" else "| low |")
        with self.assertRaisesRegex(ValueError, "confidence"):
            self.validate()

    def test_changed_wdpi_is_rejected(self):
        self.change(self.en, f'**WDPI: {self.state["wdpi"]["total"]}/100', '**WDPI: 99/100')
        with self.assertRaisesRegex(ValueError, "WDPI"):
            self.validate()

    def test_english_toc_is_not_retranslated_to_czech(self):
        _, toc = build_site.render_markdown(self.en.read_text(), {self.cs.name, self.en.name}, lang="en")
        self.assertIn("Evidence against escalation", toc)
        self.assertNotIn("Důkazy proti eskalaci", toc)

    def test_english_internal_links_prefer_available_translation(self):
        name = "2026-10-22-0700.md"
        html, _ = build_site.render_markdown(f"[Previous]({name})", {name, name.replace(".md", ".en.md")}, lang="en")
        self.assertIn('href="../reports/2026-10-22-0700.en.html"', html)

    def test_publication_allowlist_accepts_only_supported_report_variants(self):
        self.assertTrue(publish_update.ALLOWED.fullmatch("russia-escalation/reports/2026-10-22-0700.en.md"))
        for path in ["russia-escalation/reports/private.en.md", "russia-escalation/reports/2026-10-22-0700.fr.md", "experiments/2026-10-22-0700.en.md"]:
            self.assertFalse(publish_update.ALLOWED.fullmatch(path))

    def test_complete_build_switches_downloads_and_legacy_fallback(self):
        with patch.object(build_site, "ROOT", self.root), patch.object(build_site, "DATA", self.data), patch.object(check_site, "ROOT", self.root):
            build_site.build()
            check_site.check()
        site = self.root / "_site"
        cs = (site / "reports/2026-10-22-0700.html").read_text()
        en = (site / "reports/2026-10-22-0700.en.html").read_text()
        self.assertIn('<html lang="cs">', cs)
        self.assertIn('<html lang="en">', en)
        self.assertIn('href="2026-10-22-0700.en.html" lang="en" hreflang="en" aria-current="page"', en)
        self.assertIn('href="2026-10-22-0700.html" lang="cs" hreflang="cs" aria-current="page"', cs)
        self.assertIn("Older assessment (Czech only)", en)
        self.assertIn('href="2026-10-22-0700.en.md"', en)
        self.assertNotIn('class="language-switch"', (site / "reports/2026-10-21-0708.html").read_text())
        self.assertIn("Read in English", (site / "index.html").read_text())
        index = json.loads((site / "data/reports.json").read_text())
        self.assertEqual(set(index[0]["languages"]), {"cs", "en"})
        self.assertEqual(set(index[1]["languages"]), {"cs"})
        # Both pages and the archive share one state and one canonical archive item.
        self.assertEqual(json.loads((site / "data/state.json").read_text())["hypotheses"], self.state["hypotheses"])


if __name__ == "__main__":
    unittest.main()
