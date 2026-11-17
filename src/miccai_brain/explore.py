"""Graph analytics for agents: co-occurrence, coverage matrices, white-space gaps, and paper claims.

Everything here reads the built brain.sqlite and the cached LLM extractions; nothing calls a paid
model and nothing needs the query embedder (paper vectors are already stored), so an agent can
explore the brain even when the GPU server is unreachable.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import store
from .extract_llm import CACHE_DIR, load_cached

# Kinds an agent can ask for. "modality" (topic folder) and "dataset" are not in paper_concepts.
CONCEPT_KINDS = ("task", "method", "anatomy", "metric", "keyword", "body", "application", "ml")
ALL_KINDS = CONCEPT_KINDS + ("dataset", "modality")
CLAIM_KINDS = ("contribution", "limitation")

CLAIMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_claims (id INTEGER PRIMARY KEY, paper_id TEXT, kind TEXT, text TEXT);
CREATE INDEX IF NOT EXISTS paper_claims_paper ON paper_claims(paper_id);
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(text, tokenize='porter unicode61');
"""


# ---------------------------------------------------------------- claims (contributions, limitations)

def llm_claims(record: dict | None) -> list[tuple[str, str]]:
    """(kind, text) pairs for the contributions and limitations of one cached extraction."""
    if not record:
        return []
    result = record.get("result", {}) or {}
    out = []
    for key, kind in (("contributions", "contribution"), ("limitations", "limitation")):
        for text in result.get(key, []) or []:
            if isinstance(text, str) and text.strip():
                out.append((kind, text.strip()))
    return out


def load_claims(conn, root: Path | str = ".") -> int:
    """(Re)fill paper_claims from the LLM cache under root. Returns the number of claims stored."""
    conn.executescript(CLAIMS_SCHEMA)
    conn.execute("DELETE FROM paper_claims")
    conn.execute("DELETE FROM claims_fts")
    n = 0
    for (pid,) in conn.execute("SELECT paper_id FROM papers ORDER BY paper_id").fetchall():
        for kind, text in llm_claims(load_cached(Path(root), pid)):
            cur = conn.execute("INSERT INTO paper_claims (paper_id, kind, text) VALUES (?, ?, ?)", (pid, kind, text))
            conn.execute("INSERT INTO claims_fts (rowid, text) VALUES (?, ?)", (cur.lastrowid, text))
            n += 1
    conn.commit()
    return n


def has_claims(conn) -> bool:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'paper_claims'").fetchone():
        return False
    return conn.execute("SELECT 1 FROM paper_claims LIMIT 1").fetchone() is not None


class Explorer:
    """Read-only analytics over a built brain. Pass root to backfill claims from the LLM cache."""

    def __init__(self, conn, root: Path | str | None = None):
        self.conn = conn
        if not has_claims(conn) and root is not None and (Path(root) / CACHE_DIR).exists():
            load_claims(conn, root)
        self._sets: dict[tuple[str, str], set[str]] | None = None
        self._vectors: dict[str, np.ndarray] | None = None
        self._text: dict[str, str] | None = None
        self._titles = {r[0]: r[1] for r in conn.execute("SELECT paper_id, title FROM papers")}

    # ------------------------------------------------------------ indexes

    def _index(self) -> dict[tuple[str, str], set[str]]:
        """(kind, name) -> paper ids, for concepts, datasets and modalities."""
        if self._sets is None:
            sets: dict[tuple[str, str], set[str]] = defaultdict(set)
            for pid, concept, kind in self.conn.execute("SELECT paper_id, concept, kind FROM paper_concepts"):
                sets[(kind, concept)].add(pid)
            for pid, dataset in self.conn.execute("SELECT paper_id, dataset FROM paper_datasets"):
                sets[("dataset", dataset)].add(pid)
            for pid, modality in self.conn.execute("SELECT paper_id, modality FROM paper_modalities"):
                sets[("modality", modality)].add(pid)
            self._sets = dict(sets)
        return self._sets

    def _paper_vectors(self) -> dict[str, np.ndarray]:
        if self._vectors is None:
            self._vectors = {}
            rows = [(pid, store.from_blob(blob)) for pid, blob in
                    self.conn.execute("SELECT paper_id, vector FROM papers WHERE vector IS NOT NULL")]
            if rows:
                # Centre on the corpus mean: raw embeddings of medical-imaging papers all point roughly the
                # same way, so uncentred cosines are uniformly high and do not separate related from unrelated.
                mat = np.vstack([v for _, v in rows]).astype(np.float32)
                mat -= mat.mean(axis=0)
                mat /= np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9)
                self._vectors = {pid: mat[i] for i, (pid, _) in enumerate(rows)}
        return self._vectors

    def _scope(self, modality: str | None) -> set[str] | None:
        if not modality:
            return None
        hits = [pids for (k, name), pids in self._index().items() if k == "modality" and name.lower() == modality.lower()]
        return set().union(*hits) if hits else set()

    def resolve(self, name: str, kind: str | None = None) -> list[tuple[str, str]]:
        """Matching (kind, name) keys: exact (case-insensitive) first, else substring matches."""
        name_l = name.strip().lower()
        keys = [k for k in self._index() if (kind is None or k[0] == kind)]
        exact = [k for k in keys if k[1].lower() == name_l]
        if exact:
            return exact
        return sorted((k for k in keys if name_l in k[1].lower()), key=lambda k: -len(self._index()[k]))[:10]

    def papers_for(self, name: str, kind: str | None = None) -> set[str]:
        keys = self.resolve(name, kind)
        return set().union(*(self._index()[k] for k in keys)) if keys else set()

    def papers_about(self, about: str) -> set[str]:
        """Papers whose title or abstract mentions every comma-separated term; "|" separates synonyms.
        Example: "breast, MRI|magnetic resonance|DCE". This finds a paper's main subject, unlike concept
        tags, which also match benchmarks that merely include one dataset of that kind."""
        if self._text is None:
            self._text = {pid: f"{t}\n{a}".lower() for pid, t, a in
                          self.conn.execute("SELECT paper_id, title, abstract FROM papers")}
        groups = [[w.strip().lower() for w in part.split("|") if w.strip()] for part in about.split(",")]
        groups = [g for g in groups if g]
        pats = [re.compile("|".join(r"\b" + re.escape(w) for w in g)) for g in groups]
        return {pid for pid, text in self._text.items() if pats and all(p.search(text) for p in pats)}

    def select(self, concept: str | None = None, concept_kind: str | None = None, modality: str | None = None,
               about: str | None = None, paper_ids: list[str] | None = None) -> set[str] | None:
        """Intersection of every filter given; None means the whole corpus."""
        pids = None
        for part in (set(paper_ids) if paper_ids else None,
                     self.papers_for(concept, concept_kind) if concept else None,
                     self.papers_about(about) if about else None,
                     self._scope(modality)):
            if part is not None:
                pids = part if pids is None else pids & part
        return pids

    def find_papers_about(self, about: str, modality: str | None = None, limit: int = 100) -> list[dict]:
        pids = self.select(modality=modality, about=about) or set()
        return self._cite(pids, limit)

    def paper_reviews(self, paper_ids: list[str], part: str = "weaknesses", max_chars: int = 1200) -> list[dict]:
        """Compact reviews for a few papers: per reviewer the rating and the weaknesses (or the full text),
        cut to max_chars, plus the start of the meta review. Far cheaper than get_paper with reviews."""
        out = []
        for pid in paper_ids:
            reviews = []
            for section, text in self.conn.execute(
                    "SELECT section, text FROM chunks WHERE paper_id = ? AND kind = 'review' ORDER BY id", (pid,)):
                if section.startswith("author feedback"):
                    continue
                body = text
                if part == "weaknesses" and section.startswith("reviewer"):
                    m = re.search(r"Weaknesses:\s*(.*?)(?:\n\s*\n[A-Z][\w ]{2,40}:|\Z)", text, re.S)
                    body = m.group(1) if m else ""
                body = re.sub(r"\s+", " ", body).strip()
                if len(body) > max_chars:
                    body = body[:max_chars].rsplit(" ", 1)[0] + " …"
                if body:
                    reviews.append({"who": section, "text": body})
            out.append({"paper_id": pid, "title": self._titles.get(pid, ""), "reviews": reviews})
        return out

    def _items(self, kind: str, scope: set[str] | None, min_papers: int) -> dict[str, set[str]]:
        out = {}
        for (k, name), pids in self._index().items():
            if k != kind:
                continue
            pids = pids if scope is None else pids & scope
            if len(pids) >= min_papers:
                out[name] = pids
        return out

    def _cite(self, pids, limit: int = 5) -> list[dict]:
        return [{"paper_id": p, "title": self._titles.get(p, "")} for p in sorted(pids)[:limit]]

    def _centroid(self, pids) -> np.ndarray | None:
        vecs = self._paper_vectors()
        mats = [vecs[p] for p in pids if p in vecs]
        if not mats:
            return None
        c = np.mean(mats, axis=0)
        n = np.linalg.norm(c)
        return c / n if n else c

    # ------------------------------------------------------------ tools

    def vocabulary(self, kind: str, modality: str | None = None, top: int = 50, min_papers: int = 1) -> list[dict]:
        """Most frequent names of one kind (task, method, anatomy, dataset, modality, ...)."""
        items = self._items(kind, self._scope(modality), min_papers)
        ranked = sorted(items.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top]
        return [{"name": n, "papers": len(p)} for n, p in ranked]

    def neighbors(self, name: str, kind: str | None = None, other_kind: str | None = None,
                  modality: str | None = None, top: int = 20, min_together: int = 2) -> dict:
        """What co-occurs with a concept/dataset/modality, ranked by lift (observed / expected)."""
        scope = self._scope(modality)
        base = self.papers_for(name, kind)
        if scope is not None:
            base &= scope
        universe = len(scope) if scope is not None else len(self._titles)
        if not base or not universe:
            return {"name": name, "papers": 0, "neighbors": []}
        own = {k[1].lower() for k in self.resolve(name, kind)}
        rows = []
        for (k, other), pids in self._index().items():
            if (other_kind and k != other_kind) or other.lower() in own:
                continue
            pids = pids if scope is None else pids & scope
            together = len(base & pids)
            if together < min_together:
                continue
            expected = len(base) * len(pids) / universe
            rows.append({"name": other, "kind": k, "together": together, "papers": len(pids),
                         "lift": round(together / expected, 2) if expected else None})
        rows.sort(key=lambda r: (-(r["lift"] or 0) * math.log1p(r["together"]), -r["together"]))
        return {"name": name, "papers": len(base), "neighbors": rows[:top]}

    def matrix(self, row_kind: str, col_kind: str, modality: str | None = None, top_rows: int = 15,
               top_cols: int = 12, rows: list[str] | None = None, cols: list[str] | None = None) -> dict:
        """Coverage counts between two kinds (e.g. method x anatomy). Empty cells are candidate gaps."""
        scope = self._scope(modality)
        def pick(kind, names, top):
            items = self._items(kind, scope, 1)
            if names:
                return [(n, set().union(*(self._index()[k] for k in self.resolve(n, kind))) & (set(self._titles) if scope is None else scope))
                        for n in names]
            return sorted(items.items(), key=lambda kv: -len(kv[1]))[:top]
        r_items, c_items = pick(row_kind, rows, top_rows), pick(col_kind, cols, top_cols)
        grid = [[len(rp & cp) for _, cp in c_items] for _, rp in r_items]
        return {"rows": [{"name": n, "papers": len(p)} for n, p in r_items],
                "cols": [{"name": n, "papers": len(p)} for n, p in c_items], "counts": grid}

    def gaps(self, kind_a: str, kind_b: str, modality: str | None = None, min_papers: int = 5,
             max_together: int = 1, top: int = 25, focus: str | None = None) -> list[dict]:
        """White space: pairs (A, B) where both are well studied, rarely studied together, and their
        papers sit close in embedding space (so combining them is plausible, not random).
        focus restricts A to names containing that text."""
        scope = self._scope(modality)
        a_items = self._items(kind_a, scope, min_papers)
        b_items = self._items(kind_b, scope, min_papers)
        if focus:
            a_items = {n: p for n, p in a_items.items() if focus.lower() in n.lower()}
        universe = len(scope) if scope is not None else len(self._titles)
        cents = {}
        def cent(kind, name, pids):
            key = (kind, name)
            if key not in cents:
                cents[key] = self._centroid(pids)
            return cents[key]
        out = []
        for a, ap in a_items.items():
            ca = cent(kind_a, a, ap)
            for b, bp in b_items.items():
                if a.lower() == b.lower():
                    continue
                together = ap & bp
                if len(together) > max_together:
                    continue
                cb = cent(kind_b, b, bp)
                sim = float(ca @ cb) if ca is not None and cb is not None else 0.0
                expected = len(ap) * len(bp) / universe if universe else 0
                out.append({"a": a, "a_papers": len(ap), "b": b, "b_papers": len(bp), "together": len(together),
                            "expected": round(expected, 1), "semantic_closeness": round(sim, 3),
                            "score": round(max(sim, 0.0) * math.log1p(expected), 3),
                            "together_papers": self._cite(together, 3)})
        if kind_a == kind_b:  # (A, B) and (B, A) are the same pair
            seen, uniq = set(), []
            for g in sorted(out, key=lambda g: -g["score"]):
                key = frozenset((g["a"], g["b"]))
                if key not in seen:
                    seen.add(key)
                    uniq.append(g)
            out = uniq
        out.sort(key=lambda g: -g["score"])
        return out[:top]

    def bridges(self, name_a: str, name_b: str, kind_a: str | None = None, kind_b: str | None = None,
                top: int = 10) -> dict:
        """Papers that combine A and B, plus papers closest to the A-B midpoint that have only one side."""
        ap, bp = self.papers_for(name_a, kind_a), self.papers_for(name_b, kind_b)
        both = ap & bp
        ca, cb = self._centroid(ap), self._centroid(bp)
        near = []
        if ca is not None and cb is not None:
            mid = ca + cb
            mid /= np.linalg.norm(mid) or 1
            vecs = self._paper_vectors()
            cands = [(float(vecs[p] @ mid), p) for p in (ap | bp) - both if p in vecs]
            for s, p in sorted(cands, reverse=True)[:top]:
                near.append({"paper_id": p, "title": self._titles.get(p, ""), "closeness": round(s, 3),
                             "has": name_a if p in ap else name_b})
        return {"a": name_a, "a_papers": len(ap), "b": name_b, "b_papers": len(bp),
                "together": self._cite(both, top), "closest_one_sided": near}

    def claims(self, kind: str = "limitation", concept: str | None = None, concept_kind: str | None = None,
               modality: str | None = None, query: str | None = None, limit: int = 40,
               about: str | None = None, paper_ids: list[str] | None = None) -> list[dict]:
        """Contributions or limitations the LLM extracted, filtered by concept, topic, subject and/or keywords."""
        if not has_claims(self.conn):
            return []
        pids = self.select(concept, concept_kind, modality, about, paper_ids)
        params: list = [kind]
        sql = "SELECT c.paper_id, c.text FROM paper_claims c"
        if query:
            tokens = [t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", query) if len(t) > 2]
            if tokens:
                sql += " JOIN claims_fts f ON f.rowid = c.id WHERE claims_fts MATCH ? AND c.kind = ?"
                params = [" OR ".join(f'"{t}"' for t in tokens), kind]
                sql += " ORDER BY bm25(claims_fts)"
            else:
                sql += " WHERE c.kind = ?"
        else:
            sql += " WHERE c.kind = ? ORDER BY c.paper_id"
        out = []
        for pid, text in self.conn.execute(sql, params):
            if pids is not None and pid not in pids:
                continue
            out.append({"paper_id": pid, "title": self._titles.get(pid, ""), "text": text})
            if len(out) >= limit:
                break
        return out

    def claims_of(self, paper_id: str) -> dict:
        out = {"contributions": [], "limitations": []}
        if has_claims(self.conn):
            for kind, text in self.conn.execute(
                    "SELECT kind, text FROM paper_claims WHERE paper_id = ? ORDER BY id", (paper_id,)):
                out[kind + "s"].append(text)
        return out

    def limitation_themes(self, concept: str | None = None, concept_kind: str | None = None,
                          modality: str | None = None, top: int = 15, about: str | None = None,
                          paper_ids: list[str] | None = None) -> list[dict]:
        """Recurring limitation themes (keyword buckets) with example papers, for a concept or topic."""
        rows = self.claims("limitation", concept, concept_kind, modality, limit=100000, about=about, paper_ids=paper_ids)
        theme_papers: dict[str, set] = defaultdict(set)
        examples: dict[str, list] = defaultdict(list)
        for row in rows:
            text = row["text"].lower()
            for theme, pattern in LIMITATION_THEMES:
                if re.search(pattern, text):
                    theme_papers[theme].add(row["paper_id"])
                    seen = {e["paper_id"] for e in examples[theme]}
                    if len(examples[theme]) < 2 and row["paper_id"] not in seen:  # two papers, not two lines of one
                        examples[theme].append({"paper_id": row["paper_id"], "text": row["text"][:200]})
        # share = fraction of papers with at least one extracted limitation that hit this theme
        total = len({row["paper_id"] for row in rows}) or 1
        ranked = sorted(theme_papers.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top]
        return [{"theme": t, "papers": len(p), "share": round(len(p) / total, 3), "examples": examples[t]}
                for t, p in ranked]

    def reviewer_weaknesses(self, concept: str | None = None, concept_kind: str | None = None,
                            modality: str | None = None, top: int = 15, examples: int = 3,
                            about: str | None = None, paper_ids: list[str] | None = None) -> dict:
        """What reviewers criticise for papers with a concept and/or in a topic: weakness themes with the
        share of reviewed papers hit and short quotes. Uses the "Weaknesses:" part of each review."""
        pids = self.select(concept, concept_kind, modality, about, paper_ids)
        counts: Counter = Counter()
        quotes: dict[str, list] = defaultdict(list)
        reviewed = set()
        rows = self.conn.execute("SELECT paper_id, text FROM chunks WHERE kind = 'review' AND section LIKE 'reviewer%'")
        for pid, text in rows:
            if pids is not None and pid not in pids:
                continue
            m = re.search(r"Weaknesses:\s*(.*?)(?:\n\s*\n[A-Z][\w ]{2,40}:|\Z)", text, re.S)
            if not m:
                continue
            reviewed.add(pid)
            weak = m.group(1)
            hit = set()
            for sentence in re.split(r"(?<=[.!?])\s+", weak):
                low = sentence.lower()
                for theme, pattern in REVIEW_THEMES:
                    if theme not in hit and re.search(pattern, low):
                        hit.add(theme)
                        if len(quotes[theme]) < examples:
                            quotes[theme].append({"paper_id": pid, "text": sentence.strip()[:200]})
            for theme in hit:
                counts[(theme, pid)] += 1
        per_theme = Counter(theme for theme, _ in counts)
        n = len(reviewed) or 1
        return {"papers_reviewed": len(reviewed),
                "papers": sorted(reviewed)[:40] if pids is not None else "whole corpus",
                "themes": [{"theme": t, "papers": k, "share": round(k / n, 3), "examples": quotes[t]}
                           for t, k in per_theme.most_common(top)]}


REVIEW_THEMES = [
    ("limited novelty", r"novelty|incremental|combination of existing|not new|limited contribution"),
    ("missing or weak baselines", r"baselines?\b|(lack|missing|limited|no|insufficient|more) (\w+ ){0,2}comparisons?|compar\w* (with|against|to) (more|other|recent|stronger|state)|state-of-the-art|\bsota\b"),
    ("small or single-centre data", r"small (data|sample|cohort)|single[- ](cent|site|institution|dataset)|external (validation|test)|generaliz"),
    ("ablation missing", r"ablation"),
    ("statistics / significance", r"statistic|significan|confidence interval|variance|standard deviation|p-value|multiple runs|seeds?\b"),
    ("clarity / missing details", r"unclear|not (clearly )?(explained|described|defined|specified)|missing details|hard to follow|confusing"),
    ("reproducibility / code", r"reproduc|code (is )?not|release|open[- ]source|implementation details"),
    ("clinical relevance / utility", r"clinical (relevance|utility|impact|value|practice|setting)|clinically"),
    ("computational cost", r"computational|inference time|runtime|memory|flops|parameters"),
    ("evaluation metrics", r"metric|dice only|hd95|auc only|evaluation protocol"),
    ("hyperparameters / sensitivity", r"hyperparameter|sensitivity analysis|tuning"),
    ("dataset / label issues", r"label|annotation|ground truth|data split|leak"),
]


LIMITATION_THEMES = [
    ("single-centre / no external validation", r"single[- ](cent|site|institution|hospital|scanner|vendor|cohort|dataset|tracer|clinical)|"
     r"(one|two) (cent|site|institution|hospital|cohort)|external (validation|test)|multi-?(cent|site)|"
     r"limited to (a single|one|two)|generaliz\w* (to|across) other (population|cent|site|hospital|scanner)"),
    ("small dataset / sample size", r"small (data|sample|cohort|number|subset|test)|limited (data|sample|number|cohort|size)|"
     r"few (patients|cases|subjects)|\b\d{1,3} (patients|subjects|cases|participants|scans|volumes)\b"),
    ("generalisation to other modalities / anatomies", r"other (modalit|anatom|organ|disease|task)|beyond|generaliz\w* to (other|new|unseen)|not (yet )?(tested|evaluated|validated) on"),
    ("computational cost / efficiency", r"comput|memory|inference time|gpu|efficien|cost"),
    ("2D only / no 3D", r"\b2d\b|slice-?wise|not 3d|volumetric"),
    ("retrospective / no clinical or prospective evaluation", r"retrospective|prospective|clinical (validation|evaluation|trial|deployment|setting)|real-world"),
    ("baselines / comparison scope", r"baseline|comparison|compared|state-of-the-art|not best|second[- ]best|lower than|underperform"),
    ("label quality / annotation burden", r"annotat|label noise|noisy label|manual|ground truth"),
    ("interpretability", r"interpretab|explainab|black[- ]box"),
    ("hyperparameters / sensitivity", r"hyperparameter|sensitiv(e|ity) to|tuning|threshold"),
    ("dependence on pretrained / foundation models", r"pretrained|pre-trained|foundation model|frozen|\bllm|\bvlm|\bsam\b|clip|natural images"),
    ("missing modalities / paired data requirement", r"paired|missing modalit|requires? (both|multiple|all)"),
    ("fairness / demographic bias", r"fairness|bias|demographic|subgroup"),
    ("synthetic or simulated data", r"synthetic|simulat|phantom"),
    ("longitudinal / temporal", r"longitudinal|temporal|follow-?up"),
    ("uncertainty not modelled", r"uncertaint"),
]
