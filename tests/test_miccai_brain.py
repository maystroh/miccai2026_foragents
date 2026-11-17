import csv
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

from src.miccai_brain.build import build
from src.miccai_brain.chunking import chunk_paper, clean_markdown
from src.miccai_brain.corpus import extract_keywords, load_papers
from src.miccai_brain.graph import export_graph
from src.miccai_brain.search import Brain

PAPERS = {
    ("MRI", "0001-Paper1001"): ("Glioma segmentation with missing MRI modalities", "Brain",
                                "We segment glioma on BraTS with missing modalities.", "Glioma · Missing modalities · Segmentation"),
    ("MRI", "0002-Paper1002"): ("Brain tumor segmentation under incomplete modalities", "Brain",
                                "Incomplete modality brain tumor segmentation on BraTS.", "Brain tumor · Missing modalities"),
    ("EHR", "0003-Paper1003"): ("Mortality prediction from electronic health records", "Others",
                                "We predict ICU mortality on MIMIC-IV records.", "EHR · Mortality prediction"),
}


def make_corpus(root: Path):
    rows = []
    for (modality, pid), (title, body, abstract, keywords) in PAPERS.items():
        folder = root / "Published_papers" / modality / pid
        folder.mkdir(parents=True)
        url = f"https://papers.miccai.org/miccai-2026/{pid}.html"
        meta = {"paper": {"title": title, "paper_url": url, "Body": body, "Applications": "Segmentation",
                          "Machine Learning": "Deep Learning", "authors": "Doe, Jane | Roe, Rick", "abstract": abstract}}
        (folder / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        (folder / "paper.md").write_text(
            f"# {title}\n\n**Keywords:** {keywords}\n\n## 1 Introduction\n\n{abstract} More text.\n\n"
            "## 2 Method\n\nDetails of the method.\n\n## References\n\n1. Should be dropped.\n", encoding="utf-8")
        rows.append({"paper_url": url, "source_modality": modality, "kept_modality": modality})
    rows.append({"paper_url": "https://papers.miccai.org/miccai-2026/0003-Paper1003.html",
                 "source_modality": "Multimodals", "kept_modality": "EHR"})
    with (root / "Published_papers" / "deduplication_map.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["paper_url", "source_modality", "kept_modality"])
        writer.writeheader()
        writer.writerows(rows)
    reviews = root / "Published_reviews" / "MRI"
    reviews.mkdir(parents=True)
    with (reviews / "reviews.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "paper_url", "reviewer_1_strengths", "reviewer_1_weaknesses",
                                                    "reviewer_1_rating", "meta_final_decision"])
        writer.writeheader()
        writer.writerow({"title": "x", "paper_url": "https://papers.miccai.org/miccai-2026/0001-Paper1001.html",
                         "reviewer_1_strengths": "Clear writing.", "reviewer_1_weaknesses": "Limited novelty of the fusion block.",
                         "reviewer_1_rating": "(4) Weak Accept", "meta_final_decision": "Accept"})
    inputs = root / "reports" / "miccai_brain" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "datasets.csv").write_text("dataset,pattern\nBraTS,\\bBraTS\\b\nMIMIC-IV,\\bMIMIC-IV\\b\n", encoding="utf-8")
    (inputs / "concept_stoplist.csv").write_text("concept,reason\ntransformer,generic\nsegmentation,generic\n",
                                                  encoding="utf-8")
    (inputs / "concept_aliases.csv").write_text("alias,concept\nmissing modalities,missing modality\n", encoding="utf-8")


class MiccaiBrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        make_corpus(cls.root)
        llm = cls.root / "reports" / "miccai_brain" / "llm"
        llm.mkdir(parents=True)
        (llm / "0003-Paper1003.json").write_text(json.dumps({"model": "m", "prompt_version": "v1", "result": {
            "tasks": ["Mortality Prediction"], "methods": ["transformer"], "datasets": [{"name": "MIMIC-IV", "public": True},
            {"name": "eICU", "public": True}, {"name": "in-house cohort", "public": False}],
            "contributions": ["A transformer for ICU mortality."],
            "limitations": ["Single-centre retrospective cohort without external validation."]}}), encoding="utf-8")
        cls.db = cls.root / "brain.sqlite"
        build(cls.root, cls.db, "hash:128", log=lambda *_: None)
        cls.brain = Brain(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.brain.conn.close()
        cls.tmp.cleanup()

    def test_keywords_parsed_from_bold_heading_line(self):
        md = "## **Keywords:** Foundation model · Few-shot · Medical Anomaly Detection.\n"
        self.assertEqual(extract_keywords(md), ["Foundation model", "Few-shot", "Medical Anomaly Detection"])

    def test_clean_markdown_drops_references(self):
        self.assertNotIn("Should be dropped", clean_markdown("# T\n\nBody\n\n## References\n\n1. Should be dropped"))
        self.assertTrue(all("Should be dropped" not in t for _, t in chunk_paper("# T\n\nBody\n\n## References\n\nShould be dropped")))

    def test_paper_gets_every_modality_from_dedup_map(self):
        papers = {p.paper_id: p for p in load_papers(self.root)}
        self.assertEqual(papers["0003-Paper1003"].modalities, ["EHR", "Multimodals"])

    def test_search_filters_by_modality_and_ranks_relevant_first(self):
        hits = self.brain.search("glioma missing modalities", limit=3)
        self.assertEqual(hits[0].paper_id, "0001-Paper1001")
        ehr = self.brain.search("segmentation", modality="EHR")
        self.assertTrue(all("EHR" in h.modalities for h in ehr))

    def test_reviews_searchable_only_when_asked(self):
        self.assertFalse(any(h.kind == "review" for h in self.brain.search("novelty fusion block")))
        hits = self.brain.search("novelty fusion block", include_reviews=True)
        self.assertEqual(hits[0].kind, "review")

    def test_concepts_aliases_and_datasets(self):
        paper = self.brain.paper("0001-Paper1001")
        self.assertIn("missing modality", [c["concept"] for c in paper["concepts"]])
        self.assertEqual([d["dataset"] for d in paper["datasets"]], ["BraTS"])
        self.assertEqual(paper["decision"], "Accept")
        self.assertEqual(len(paper["reviews"]), 1)

    def test_cached_llm_extraction_merges_concepts_and_datasets(self):
        paper = self.brain.paper("0003-Paper1003")
        kinds = {(c["concept"], c["kind"]) for c in paper["concepts"]}
        self.assertIn("mortality prediction", {c for c, _ in kinds})
        self.assertEqual(sorted(d["dataset"] for d in paper["datasets"]), ["MIMIC-IV", "eICU"])

    def test_stoplist_drops_generic_terms_but_keeps_miccai_tags(self):
        concepts = {(c["concept"], c["kind"]) for c in self.brain.paper("0003-Paper1003")["concepts"]}
        self.assertNotIn(("transformer", "method"), concepts)
        self.assertIn(("segmentation", "application"), concepts)  # MICCAI tag kept
        keywords = {c["concept"] for c in self.brain.paper("0001-Paper1001")["concepts"] if c["kind"] == "keyword"}
        self.assertNotIn("segmentation", keywords)

    def test_graph_export_links_shared_concepts(self):
        graph = export_graph(self.brain.conn)
        names = [c["n"] for c in graph["concepts"]]
        self.assertIn("missing modality", names)  # shared by two papers
        self.assertEqual({d["n"] for d in graph["datasets"]}, {"BraTS", "MIMIC-IV", "eICU"})
        self.assertTrue(graph["edges"])


    def test_claims_stored_and_filtered(self):
        from src.miccai_brain.explore import Explorer
        ex = Explorer(self.brain.conn)
        lims = ex.claims("limitation", modality="EHR")
        self.assertEqual([c["paper_id"] for c in lims], ["0003-Paper1003"])
        self.assertEqual(ex.claims("limitation", modality="MRI"), [])
        self.assertEqual(ex.claims("limitation", query="external validation")[0]["paper_id"], "0003-Paper1003")
        self.assertEqual(ex.claims_of("0003-Paper1003")["contributions"], ["A transformer for ICU mortality."])
        themes = {t["theme"] for t in ex.limitation_themes()}
        self.assertIn("single-centre / no external validation", themes)

    def test_neighbors_matrix_and_gaps(self):
        from src.miccai_brain.explore import Explorer
        ex = Explorer(self.brain.conn)
        near = ex.neighbors("BraTS", "dataset", other_kind="modality", top=5)
        self.assertEqual(near["papers"], 2)
        self.assertEqual(near["neighbors"][0]["name"], "MRI")
        grid = ex.matrix("dataset", "modality")
        cols = [c["name"] for c in grid["cols"]]
        rows = [r["name"] for r in grid["rows"]]
        self.assertEqual(grid["counts"][rows.index("BraTS")][cols.index("EHR")], 0)
        gaps = ex.gaps("dataset", "modality", min_papers=1, max_together=0)
        self.assertIn(("BraTS", "EHR"), {(g["a"], g["b"]) for g in gaps})
        self.assertNotIn(("BraTS", "MRI"), {(g["a"], g["b"]) for g in gaps})
        bridge = ex.bridges("BraTS", "MRI")
        self.assertEqual(len(bridge["together"]), 2)

    def test_limitation_themes_count_distinct_papers(self):
        from src.miccai_brain.explore import Explorer
        ex = Explorer(self.brain.conn)
        conn = self.brain.conn
        conn.execute("INSERT INTO paper_claims (paper_id, kind, text) VALUES ('0003-Paper1003', 'limitation', 'Single-centre cohort only.')")
        try:
            theme = next(t for t in ex.limitation_themes() if t["theme"].startswith("single-centre"))
            self.assertEqual((theme["papers"], theme["share"]), (1, 1.0))
        finally:
            conn.execute("DELETE FROM paper_claims WHERE text = 'Single-centre cohort only.'")

    def test_matrix_with_unknown_modality_is_empty(self):
        from src.miccai_brain.explore import Explorer
        grid = Explorer(self.brain.conn).matrix("dataset", "modality", modality="UNKNOWN", rows=["BraTS"], cols=["MRI"])
        self.assertEqual(grid["counts"], [[0]])

    def test_mcp_server_registers_every_tool_once(self):
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp not installed")
        import asyncio
        from src.miccai_brain.mcp_server import create_server
        names = [t.name for t in asyncio.run(create_server(self.db, self.root).list_tools())]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("reviewer_weaknesses", names)

    def test_reviewer_weaknesses_themes(self):
        from src.miccai_brain.explore import Explorer
        out = Explorer(self.brain.conn).reviewer_weaknesses(modality="MRI")
        self.assertEqual(out["papers_reviewed"], 1)
        self.assertEqual(out["themes"][0]["theme"], "limited novelty")
        self.assertEqual(Explorer(self.brain.conn).reviewer_weaknesses(modality="EHR")["papers_reviewed"], 0)

    def test_hybrid_search_falls_back_to_keywords_when_embedder_fails(self):
        brain = Brain(self.db)
        brain._embedder = FailingEmbedder(0)
        hits = brain.search("glioma")
        self.assertTrue(hits)
        self.assertIn("keyword results only", brain.last_warning)
        brain.conn.close()


class ConceptMergeTest(unittest.TestCase):
    def test_spelling_variants_fold_to_the_most_common_form(self):
        from src.miccai_brain.extract import fold_key, merge_variants
        self.assertEqual(fold_key("Multi-modal LLMs"), fold_key("multimodal llm"))
        self.assertNotEqual(fold_key("class"), fold_key("cla"))
        mapping = merge_variants({"a": [("f1 score", "metric")], "b": [("f1 score", "metric")],
                                  "c": [("f1-score", "metric"), ("state-space models", "keyword")],
                                  "d": [("state space model", "method")]})
        self.assertEqual(mapping, {"f1-score": "f1 score", "state-space models": "state space model"})

    def test_stoplist_matches_any_spelling(self):
        from src.miccai_brain.extract import fold_key, is_stopped
        keys = {fold_key(s) for s in ["3d u-net", "resnet-50", "multilayer perceptron", "neural network", "lung"]}
        for term in ["3d unet", "resnet50", "multi-layer perceptron", "neural networks", "lungs"]:
            self.assertTrue(is_stopped(term, keys), term)
        self.assertFalse(is_stopped("liver", keys))

    def test_majority_kind_keeps_a_method_visible(self):
        from src.miccai_brain.extract import majority_kinds
        per_paper = {f"m{i}": [("grad-cam", "method")] for i in range(9)}
        per_paper.update({f"x{i}": [("grad-cam", "metric")] for i in range(2)})
        per_paper["t"] = [("probe", "metric")]
        per_paper["u"] = [("probe", "method")]
        self.assertEqual(majority_kinds(per_paper), {"grad-cam": "method", "probe": "method"})
        # Merged spellings in one paper count once.
        merged = {"a": [("grad-cam", "method")], "b": [("grad-cam", "method")], "c": [("grad-cam", "metric")] * 3}
        self.assertEqual(majority_kinds(merged), {"grad-cam": "method"})

    def test_body_tags_are_split_and_win_over_keywords(self):
        from src.miccai_brain.corpus import Paper
        from src.miccai_brain.extract import paper_concepts
        paper = Paper(paper_id="p", title="t", paper_url="u", body="Abdomen; Brain", keywords=["Brain", "Registration"])
        self.assertEqual(paper_concepts(paper, {}),
                         [("abdomen", "body"), ("brain", "body"), ("registration", "keyword")])


if __name__ == "__main__":
    unittest.main()


FAKE_SERVER = """
import base64, json, sys
import numpy as np
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    req = json.loads(line)
    vec = np.ones((len(req["texts"]), 4), dtype=np.float16) * (2 if req["query"] else 1)
    print(json.dumps({"vectors": base64.b64encode(vec.tobytes()).decode(), "shape": list(vec.shape)}), flush=True)
"""


class SshEmbedderTest(unittest.TestCase):
    def test_speaks_server_embed_protocol(self):
        from src.miccai_brain.embed import get_embedder
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            script = Path(tmp) / "server.py"
            script.write_text(FAKE_SERVER, encoding="utf-8")
            env = {"MICCAI_BRAIN_SSH": "{remote}", "MICCAI_BRAIN_SSH_REMOTE": f'"{sys.executable}" "{script}"'}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                embedder = get_embedder("ssh:test-model")
                vectors = embedder.embed(["a"] * 70, query=True)
                embedder.close()
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        self.assertEqual(embedder.dim, 4)
        self.assertEqual(vectors.shape, (70, 4))
        self.assertAlmostEqual(float((vectors[0] ** 2).sum()), 1.0, places=5)


class FailingEmbedder:
    spec, dim = "failing", 4

    def __init__(self, fail_after):
        self.calls, self.fail_after = 0, fail_after

    def embed(self, texts, query=False):
        import numpy as np
        self.calls += 1
        if self.calls > self.fail_after:
            raise ConnectionError("server went away")
        return np.ones((len(texts), 4), dtype="float32") / 2


class RobustnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        make_corpus(self.root)
        self.db = self.root / "brain.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_failed_rebuild_keeps_previous_index(self):
        from unittest import mock
        from src.miccai_brain import build as build_mod
        build(self.root, self.db, "hash:64", log=lambda *_: None)
        with mock.patch.object(build_mod, "get_embedder", return_value=FailingEmbedder(1)), \
                mock.patch.dict(os.environ, {"MICCAI_BRAIN_BUILD_BATCH": "2"}):
            with self.assertRaises(ConnectionError):
                build(self.root, self.db, "failing", log=lambda *_: None)
        brain = Brain(self.db)
        try:
            self.assertGreater(brain.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0], 0)
            self.assertEqual(brain.search("glioma")[0].paper_id, "0001-Paper1001")
        finally:
            brain.conn.close()
        self.assertFalse(self.db.with_name(self.db.name + ".building").exists())

    def test_bm25_filters_modality_before_cutoff(self):
        build(self.root, self.db, "hash:64", log=lambda *_: None)
        brain = Brain(self.db)
        try:
            hits = brain._bm25("segmentation segmentation glioma mortality", {"abstract", "body"}, "EHR", limit=1)
            self.assertEqual({pid for _, pid in hits}, {"0003-Paper1003"})
        finally:
            brain.conn.close()

    def test_budget_stops_scheduling_new_requests(self):
        from unittest import mock
        from src.miccai_brain import extract_llm
        papers = load_papers(self.root) * 10  # 30 papers
        calls = []

        def fake_call(prompt, model):
            calls.append(1)
            return {"tasks": ["x"]}, {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.02}

        with mock.patch.object(extract_llm, "call_llm", fake_call):
            usage = extract_llm.extract_all(self.root, papers, "m", workers=4, force=True,
                                            max_cost=0.01, log=lambda *_: None)
        self.assertTrue(usage["stopped_by_budget"])
        self.assertLessEqual(len(calls), 4)  # only the first in-flight batch
