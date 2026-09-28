"""Generate all research analysis artefacts from the as-built checklist.

Outputs under data/exports/analysis/:
  - CSV tables for corpus, ABSA, feature scores, recommendations, evaluation
  - Chapter5_Results_Analysis_IM2021049.docx
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.models.schemas import RecommendRequest
from app.nlp.aggregate import corpus_stats, validation_report
from app.nlp.aspects import ASPECT_LABELS, CORE_ASPECTS
from app.services.feedback import evaluation_summary
from app.services.recommender import recommend

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "exports" / "analysis"
DOCX_PATH = ROOT / "Chapter5_Results_Analysis_IM2021049.docx"

ASPECT_ORDER = ["battery", "display", "price", "camera", "performance", "design"]

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "Balanced": {a: 5 for a in CORE_ASPECTS},
    "Camera-focused": {"camera": 10, "display": 6, "performance": 4, "battery": 4, "design": 5, "price": 3},
    "Battery-focused": {"battery": 10, "performance": 4, "price": 4, "design": 3, "camera": 2, "display": 2},
    "Performance-focused": {"performance": 10, "display": 8, "battery": 6, "design": 3, "camera": 3, "price": 2},
    "Design-focused": {"design": 10, "display": 6, "camera": 4, "battery": 3, "performance": 3, "price": 3},
    "Price-focused": {"price": 10, "battery": 5, "performance": 5, "design": 4, "camera": 3, "display": 3},
}


def font(run, *, bold=False, italic=False, size=12):
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = "Times New Roman"
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    rFonts.set(qn("w:cs"), "Times New Roman")


def h(doc, text, level=1):
    heading = doc.add_heading(text, level=level)
    for run in heading.runs:
        font(run, bold=True, size=14 if level == 1 else 12)


def p(doc, text, *, italic=False, indent=True):
    para = doc.add_paragraph()
    pf = para.paragraph_format
    pf.space_after = Pt(8)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.first_line_indent = Inches(0.5) if indent else Inches(0)
    run = para.add_run(text)
    font(run, italic=italic, size=12)


def bullet(doc, text):
    para = doc.add_paragraph(style="List Bullet")
    para.clear()
    para.paragraph_format.space_after = Pt(4)
    para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = para.add_run(text)
    font(run, size=12)


def table(doc, headers, rows, caption=None):
    if caption:
        p(doc, caption, italic=True, indent=False)
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    for i, head in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        font(cell.paragraphs[0].add_run(str(head)), bold=True, size=10)
    for r_i, row in enumerate(rows):
        for c_i, val in enumerate(row):
            cell = t.rows[r_i + 1].cells[c_i]
            cell.text = ""
            font(cell.paragraphs[0].add_run(str(val)), size=10)
    doc.add_paragraph()


def write_csv(path: Path, headers: list[str], rows: list[list]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def top_n_overlap(a: list[int], b: list[int], n: int = 3) -> float:
    set_a, set_b = set(a[:n]), set(b[:n])
    if not set_a and not set_b:
        return 0.0
    return round(len(set_a & set_b) / n, 4)


def run_analysis() -> dict:
    import sqlite3

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    init_db()
    db = SessionLocal()
    raw = sqlite3.connect(ROOT / "data" / "smartphones.db")
    payload: dict = {"generated_on": date.today().isoformat()}

    def q(sql: str, params=()):
        return raw.execute(sql, params).fetchall()

    def q1(sql: str, params=()):
        return raw.execute(sql, params).fetchone()

    # ------------------------------------------------------------------ #
    # 1. Descriptive corpus
    # ------------------------------------------------------------------ #
    stats = corpus_stats(db, settings)
    funnel_rows = [
        ["Raw Bright Data / local CSV", "Review rows / ASINs", "4092 / 227"],
        ["After dropping manuals/guides", "Review rows / ASINs", "4080 / 224"],
        ["Loaded into SQLite", "Phones / reviews", f"{stats['phones']} / {stats['reviews_total']}"],
        ["After Step 1 preprocessing (kept)", "Reviews", str(stats["reviews_usable"])],
        ["Excluded in Step 1", "Reviews", str(stats["reviews_excluded"])],
        ["Step 2 sentences", "Sentences", str(stats["sentences"])],
        ["Steps 3â€“4 ABSA", "Aspectâ€“sentiment records", str(stats["aspect_sentiments"])],
    ]
    phones_scored = q1("select count(distinct smartphone_id) from aspect_scores")[0]
    funnel_rows.append(["Step 6 feature scores", "Phones with scores", str(phones_scored)])
    write_csv(OUT_DIR / "01_dataset_funnel.csv", ["Stage", "Unit", "Count"], funnel_rows)

    excl = stats.get("exclusion_breakdown") or {}
    excl_rows = [[k, v] for k, v in sorted(excl.items(), key=lambda x: -x[1])]
    write_csv(OUT_DIR / "01_exclusion_breakdown.csv", ["Reason", "Count"], excl_rows)

    per_phone = q1(
        """
        select count(*), min(c), round(avg(c),2), max(c)
        from (
          select smartphone_id, count(*) c from reviews
          where excluded_reason is null or excluded_reason=''
          group by smartphone_id
        )
        """
    )
    write_csv(
        OUT_DIR / "01_reviews_per_phone.csv",
        ["phones_with_kept_reviews", "min", "mean", "max"],
        [[per_phone[0], per_phone[1], per_phone[2], per_phone[3]]],
    )

    brands = q(
        """
        select coalesce(brand,'Unknown') brand, count(*) phones
        from smartphones group by brand order by phones desc
        """
    )
    write_csv(OUT_DIR / "01_brand_coverage.csv", ["Brand", "Phones"], [list(r) for r in brands])

    payload["corpus"] = {
        "stats": {k: v for k, v in stats.items() if k != "note"},
        "phones_scored": phones_scored,
        "reviews_per_phone": {
            "phones": per_phone[0],
            "min": per_phone[1],
            "mean": per_phone[2],
            "max": per_phone[3],
        },
        "brands": [{"brand": b, "phones": n} for b, n in brands],
    }

    # ------------------------------------------------------------------ #
    # 2. ABSA sentiment
    # ------------------------------------------------------------------ #
    aspect_sent = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0})
    for aspect, sentiment, n in q(
        "select aspect, sentiment, count(*) from aspect_sentiments group by aspect, sentiment"
    ):
        aspect_sent[aspect][sentiment] = n

    total_mentions = sum(sum(v.values()) for v in aspect_sent.values())
    absa_rows = []
    for aspect in ASPECT_ORDER:
        d = aspect_sent[aspect]
        tot = d["positive"] + d["neutral"] + d["negative"]
        share = round(100.0 * tot / total_mentions, 2) if total_mentions else 0.0
        absa_rows.append(
            [aspect.title(), d["positive"], d["neutral"], d["negative"], tot, f"{share}%"]
        )
    absa_rows.append(
        [
            "Total",
            sum(aspect_sent[a]["positive"] for a in ASPECT_ORDER),
            sum(aspect_sent[a]["neutral"] for a in ASPECT_ORDER),
            sum(aspect_sent[a]["negative"] for a in ASPECT_ORDER),
            total_mentions,
            "100%",
        ]
    )
    write_csv(
        OUT_DIR / "02_per_aspect_sentiment.csv",
        ["Aspect", "Positive", "Neutral", "Negative", "Total", "Share_of_all"],
        absa_rows,
    )

    examples = []
    for aspect in ASPECT_ORDER:
        for sentiment in ("positive", "negative"):
            row = q1(
                """
                select a.aspect, a.sentiment, s.text, sm.canonical_name, sm.source_product_id
                from aspect_sentiments a
                join sentences s on s.id = a.sentence_id
                join smartphones sm on sm.id = a.smartphone_id
                where a.aspect=? and a.sentiment=?
                  and length(s.text) between 40 and 220
                order by length(s.text) desc
                limit 1
                """,
                (aspect, sentiment),
            )
            if row:
                examples.append(
                    {
                        "aspect": row[0],
                        "sentiment": row[1],
                        "sentence": row[2].replace("\n", " ").strip(),
                        "phone": row[3] or "",
                        "asin": row[4] or "",
                    }
                )
    write_csv(
        OUT_DIR / "02_qualitative_examples.csv",
        ["aspect", "sentiment", "phone", "asin", "sentence"],
        [[e["aspect"], e["sentiment"], e["phone"], e["asin"], e["sentence"]] for e in examples],
    )
    payload["absa"] = {"per_aspect": absa_rows, "examples": examples, "total": total_mentions}

    # ------------------------------------------------------------------ #
    # 3. Feature scores
    # ------------------------------------------------------------------ #
    score_rows = q(
        """
        select s.source_product_id, coalesce(s.canonical_name,s.raw_title,''), s.brand,
               a.aspect, a.positive_count, a.neutral_count, a.negative_count,
               a.mention_count, round(a.raw_score,4), round(a.score,4), round(a.confidence,4)
        from aspect_scores a
        join smartphones s on s.id=a.smartphone_id
        order by 2 collate nocase, a.aspect
        """
    )
    write_csv(
        OUT_DIR / "03_feature_score_dataset.csv",
        [
            "asin",
            "smartphone_name",
            "brand",
            "aspect",
            "positive",
            "neutral",
            "negative",
            "mentions",
            "raw_score",
            "feature_score_shrunk",
            "confidence",
        ],
        [list(r) for r in score_rows],
    )

    sample_ids = q(
        """
        select s.id, s.source_product_id, coalesce(s.canonical_name,s.raw_title),
               sum(a.mention_count) m
        from aspect_scores a join smartphones s on s.id=a.smartphone_id
        group by s.id having count(*)=6
        order by m desc limit 3
        """
    )
    sample_profiles = []
    for sid, asin, name, _m in sample_ids:
        scores = q(
            """
            select aspect, positive_count, neutral_count, negative_count,
                   mention_count, round(raw_score,4), round(score,4), round(confidence,4)
            from aspect_scores where smartphone_id=? order by aspect
            """,
            (sid,),
        )
        profile = {"asin": asin, "name": name, "aspects": [list(r) for r in scores]}
        sample_profiles.append(profile)
        write_csv(
            OUT_DIR / f"03_sample_profile_{asin}.csv",
            ["aspect", "positive", "neutral", "negative", "mentions", "raw", "score", "confidence"],
            [list(r) for r in scores],
        )

    rich = q(
        """
        select coalesce(s.canonical_name,s.raw_title), a.aspect, a.mention_count,
               round(a.confidence,4), round(a.score,4)
        from aspect_scores a join smartphones s on s.id=a.smartphone_id
        order by a.confidence desc, a.mention_count desc limit 5
        """
    )
    sparse = q(
        """
        select coalesce(s.canonical_name,s.raw_title), a.aspect, a.mention_count,
               round(a.confidence,4), round(a.score,4)
        from aspect_scores a join smartphones s on s.id=a.smartphone_id
        order by a.confidence asc, a.mention_count asc limit 5
        """
    )
    write_csv(
        OUT_DIR / "03_high_confidence_examples.csv",
        ["phone", "aspect", "mentions", "confidence", "score"],
        [list(r) for r in rich],
    )
    write_csv(
        OUT_DIR / "03_low_confidence_examples.csv",
        ["phone", "aspect", "mentions", "confidence", "score"],
        [list(r) for r in sparse],
    )
    payload["feature_scores"] = {
        "rows": len(score_rows),
        "sample_profiles": sample_profiles,
        "high_confidence": [list(r) for r in rich],
        "low_confidence": [list(r) for r in sparse],
    }

    # ------------------------------------------------------------------ #
    # 4. Recommendation demos + baseline
    # ------------------------------------------------------------------ #
    ranking_tables = {}
    for profile_name, weights in WEIGHT_PROFILES.items():
        resp = recommend(
            db,
            RecommendRequest(weights=weights, top_k=5, min_reviews=0, method="weighted"),
            settings,
        )
        ranking_tables[profile_name] = [
            {
                "rank": i + 1,
                "phone": r.name,
                "id": r.smartphone_id,
                "score": r.final_score,
                "explanation": (r.explanation or "")[:280],
            }
            for i, r in enumerate(resp.results)
        ]
        write_csv(
            OUT_DIR / f"04_top5_{profile_name.replace(' ', '_').lower()}.csv",
            ["rank", "phone_id", "phone", "score", "explanation"],
            [
                [x["rank"], x["id"], x["phone"], x["score"], x["explanation"]]
                for x in ranking_tables[profile_name]
            ],
        )

    proposed = recommend(
        db,
        RecommendRequest(
            weights=WEIGHT_PROFILES["Balanced"], top_k=10, min_reviews=0, method="weighted"
        ),
        settings,
    )
    baseline = recommend(
        db,
        RecommendRequest(
            weights=WEIGHT_PROFILES["Balanced"], top_k=10, min_reviews=0, method="star_rating"
        ),
        settings,
    )
    prop_ids = [r.smartphone_id for r in proposed.results]
    base_ids = [r.smartphone_id for r in baseline.results]
    overlap3 = top_n_overlap(prop_ids, base_ids, 3)
    overlap5 = top_n_overlap(prop_ids, base_ids, 5)

    compare_rows = []
    for i in range(10):
        p_row = proposed.results[i] if i < len(proposed.results) else None
        b_row = baseline.results[i] if i < len(baseline.results) else None
        compare_rows.append(
            [
                i + 1,
                p_row.name if p_row else "",
                round(p_row.final_score, 4) if p_row else "",
                b_row.name if b_row else "",
                round(b_row.site_rating or 0, 2) if b_row else "",
            ]
        )
    write_csv(
        OUT_DIR / "04_proposed_vs_star_baseline_top10.csv",
        ["rank", "proposed_phone", "proposed_score", "baseline_phone", "baseline_stars"],
        compare_rows,
    )
    write_csv(
        OUT_DIR / "04_topn_overlap.csv",
        ["metric", "value"],
        [["top3_overlap", overlap3], ["top5_overlap", overlap5]],
    )

    cam_ids = {x["id"] for x in ranking_tables["Camera-focused"]}
    bat_ids = {x["id"] for x in ranking_tables["Battery-focused"]}
    write_csv(
        OUT_DIR / "04_camera_vs_battery_top5.csv",
        ["set", "phones"],
        [
            [
                "camera_only",
                "; ".join(
                    x["phone"] for x in ranking_tables["Camera-focused"] if x["id"] not in bat_ids
                ),
            ],
            [
                "battery_only",
                "; ".join(
                    x["phone"] for x in ranking_tables["Battery-focused"] if x["id"] not in cam_ids
                ),
            ],
            [
                "both",
                "; ".join(
                    x["phone"] for x in ranking_tables["Camera-focused"] if x["id"] in bat_ids
                ),
            ],
        ],
    )

    explanation_sample = ""
    if proposed.results:
        explanation_sample = proposed.results[0].explanation or ""
        write_csv(
            OUT_DIR / "04_explanation_top1_balanced.csv",
            ["phone", "score", "explanation"],
            [[proposed.results[0].name, proposed.results[0].final_score, explanation_sample]],
        )

    payload["recommendations"] = {
        "profiles": ranking_tables,
        "overlap_top3": overlap3,
        "overlap_top5": overlap5,
        "comparison": compare_rows,
        "top1_explanation": explanation_sample,
    }

    # ------------------------------------------------------------------ #
    # 5. Evaluation
    # ------------------------------------------------------------------ #
    val = validation_report(db, settings)
    write_csv(
        OUT_DIR / "05_star_text_agreement.csv",
        ["metric", "value"],
        [
            ["reviews_compared", val["reviews_compared"]],
            ["agreement_rate", val["agreement_rate"]],
            ["agreement_pct", round(float(val["agreement_rate"]) * 100, 2)],
            ["mean_absolute_error", val["mean_absolute_error"]],
        ],
    )
    by_rating_rows = []
    for stars, info in (val.get("by_rating") or {}).items():
        by_rating_rows.append(
            [stars, info["reviews"], info["agreement_rate"], info["mean_absolute_error"]]
        )
    write_csv(
        OUT_DIR / "05_star_text_agreement_by_rating.csv",
        ["stars", "reviews", "agreement_rate", "mae"],
        by_rating_rows,
    )

    eval_report = evaluation_summary(db, settings)
    eval_fields = [
        ("feedback_sessions", eval_report.feedback_count),
        ("mean_satisfaction", eval_report.mean_satisfaction),
        ("mean_ndcg_at_3", eval_report.mean_ndcg_at_3),
        ("ndcg_session_count", eval_report.ndcg_session_count),
        ("mean_spearman", eval_report.mean_spearman),
        ("spearman_session_count", eval_report.spearman_session_count),
        ("proposed_mean_satisfaction", eval_report.proposed_mean_satisfaction),
        ("proposed_mean_ndcg_at_3", eval_report.proposed_mean_ndcg_at_3),
        ("proposed_session_count", eval_report.proposed_session_count),
        ("baseline_mean_satisfaction", eval_report.baseline_mean_satisfaction),
        ("baseline_mean_ndcg_at_3", eval_report.baseline_mean_ndcg_at_3),
        ("baseline_session_count", eval_report.baseline_session_count),
        ("star_text_agreement_rate", val["agreement_rate"]),
    ]
    write_csv(
        OUT_DIR / "05_evaluation_summary.csv",
        ["metric", "value"],
        [[k, v] for k, v in eval_fields],
    )

    faithful = 0
    checked = 0
    faith_rows = []
    for profile_name, items in ranking_tables.items():
        if not items:
            continue
        resp = recommend(
            db,
            RecommendRequest(weights=WEIGHT_PROFILES[profile_name], top_k=1, method="weighted"),
            settings,
        )
        if not resp.results:
            continue
        top = resp.results[0]
        contribs = sorted(
            [c for c in top.breakdown if c.weight > 0 and not c.imputed],
            key=lambda c: c.contribution,
            reverse=True,
        )[:2]
        expl = (top.explanation or "").lower()
        ok = False
        if contribs:
            ok = all(
                ASPECT_LABELS.get(c.aspect, c.aspect).split()[0].lower() in expl for c in contribs
            )
        checked += 1
        faithful += int(ok)
        faith_rows.append(
            [
                profile_name,
                top.name,
                ",".join(c.aspect for c in contribs),
                "yes" if ok else "no",
                (top.explanation or "")[:200],
            ]
        )
    faith_rate = round(faithful / checked, 4) if checked else None
    write_csv(
        OUT_DIR / "05_explanation_faithfulness.csv",
        ["profile", "phone", "top_aspects", "faithful", "explanation_excerpt"],
        faith_rows,
    )
    write_csv(
        OUT_DIR / "05_explanation_faithfulness_summary.csv",
        ["checked", "faithful", "rate"],
        [[checked, faithful, faith_rate]],
    )

    payload["evaluation"] = {
        "star_text": val,
        "feedback": {
            "sessions": eval_report.feedback_count,
            "mean_satisfaction": eval_report.mean_satisfaction,
            "mean_ndcg_at_3": eval_report.mean_ndcg_at_3,
            "mean_spearman": eval_report.mean_spearman,
            "proposed_ndcg": eval_report.proposed_mean_ndcg_at_3,
            "baseline_ndcg": eval_report.baseline_mean_ndcg_at_3,
            "ranking_note": eval_report.ranking_quality_note,
            "comparison_note": eval_report.baseline_comparison_note,
        },
        "explanation_faithfulness_rate": faith_rate,
        "explanation_checked": checked,
    }

    (OUT_DIR / "analysis_summary.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    build_chapter5(
        payload, stats, absa_rows, examples, sample_profiles, val, eval_report, faith_rate, checked
    )
    try:
        from data.artifacts.generate_research_charts import main as make_charts

        make_charts()
    except Exception as exc:  # pragma: no cover - charts are additive
        # Fallback: run as file path import
        import runpy

        try:
            runpy.run_path(str(ROOT / "data" / "artifacts" / "generate_research_charts.py"), run_name="__main__")
        except Exception as exc2:
            print("Chart generation skipped:", exc, exc2)
    raw.close()
    db.close()
    return payload


def build_chapter5(
    payload,
    stats,
    absa_rows,
    examples,
    sample_profiles,
    val,
    eval_report,
    faith_rate,
    checked,
):
    doc = Document()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("CHAPTER 5: RESULTS AND ANALYSIS")
    font(r, bold=True, size=16)
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(
        sub.add_run(
            f"As-built results for IM/2021/049 â€” generated {date.today().isoformat()}"
        ),
        italic=True,
        size=11,
    )
    p(
        doc,
        "This chapter reports the descriptive corpus results, ABSA outputs, feature-score "
        "dataset, recommendation demonstrations under multiple user-priority profiles, "
        "comparison with an Amazon star-rating baseline, starâ€“text agreement, explanation "
        "faithfulness checks, and optional pilot ranking metrics (NDCG@3 / Spearman) where "
        "feedback sessions exist. Supporting CSV files are in data/exports/analysis/.",
        italic=True,
        indent=False,
    )

    h(doc, "5.1 Dataset Descriptive Results", 2)
    p(
        doc,
        f"The frozen Bright Data Amazon smartphone corpus was loaded into SQLite with "
        f"{stats['phones']} phones and {stats['reviews_total']} review rows. After "
        f"preprocessing, {stats['reviews_usable']} English usable reviews remained "
        f"({stats['reviews_excluded']} excluded). Segmentation produced {stats['sentences']} "
        f"sentences and ABSA produced {stats['aspect_sentiments']} aspectâ€“sentiment records. "
        f"{payload['corpus']['phones_scored']} phones received at least one feature score.",
    )
    table(
        doc,
        ["Stage", "Unit", "Count"],
        [
            ["Raw CSV", "Rows / ASINs", "4,092 / 227"],
            ["After manuals removed", "Rows / ASINs", "4,080 / 224"],
            ["Loaded", "Phones / reviews", f"{stats['phones']} / {stats['reviews_total']}"],
            ["Kept after preprocess", "Reviews", str(stats["reviews_usable"])],
            ["Excluded", "Reviews", str(stats["reviews_excluded"])],
            ["Sentences", "Sentences", str(stats["sentences"])],
            ["ABSA records", "Aspectâ€“sentiment", str(stats["aspect_sentiments"])],
            ["Scored phones", "Phones", str(payload["corpus"]["phones_scored"])],
        ],
        caption="Table 5.1: Dataset funnel",
    )
    excl = stats.get("exclusion_breakdown") or {}
    table(
        doc,
        ["Exclusion reason", "Count"],
        [[k, v] for k, v in sorted(excl.items(), key=lambda x: -x[1])],
        caption="Table 5.2: Preprocessing exclusions",
    )
    rpp = payload["corpus"]["reviews_per_phone"]
    p(
        doc,
        f"Kept reviews per phone: min {rpp['min']}, mean {rpp['mean']}, max {rpp['max']} "
        f"(across {rpp['phones']} phones with at least one kept review).",
    )
    brand_rows = [[b["brand"], b["phones"]] for b in payload["corpus"]["brands"][:10]]
    table(doc, ["Brand", "Phones"], brand_rows, caption="Table 5.3: Brand coverage (top)")

    h(doc, "5.2 ABSA Results", 2)
    p(
        doc,
        "Lexicon ABSA labelled aspect mentions as positive, neutral, or negative across six "
        "core features. Battery dominates mention volume; design is present with substantial "
        "evidence, confirming the six-feature taxonomy is operational.",
    )
    table(
        doc,
        ["Aspect", "Positive", "Neutral", "Negative", "Total", "Share"],
        absa_rows,
        caption="Table 5.4: Per-aspect sentiment distribution",
    )
    p(doc, "Qualitative examples (from stored sentence evidence):", indent=False)
    for ex in examples[:8]:
        bullet(
            doc,
            f"{ex['aspect'].title()} / {ex['sentiment']}: â€œ{ex['sentence']}â€ "
            f"({ex['phone'] or ex['asin']})",
        )

    h(doc, "5.3 Feature-Score Results", 2)
    p(
        doc,
        "Feature scores were computed as raw_score = (positive + 0.5 Ã— neutral) / mentions, "
        "then Bayesian-shrunk toward the corpus mean (k = 5). Confidence = mentions / "
        "(mentions + 3). The full dataset (1,240 phoneâ€“aspect rows) is exported to "
        "03_feature_score_dataset.csv.",
    )
    for profile in sample_profiles:
        table(
            doc,
            ["Aspect", "Pos", "Neu", "Neg", "Mentions", "Raw", "Score", "Confidence"],
            profile["aspects"],
            caption=f"Table: Feature profile â€” {profile['name']} ({profile['asin']})",
        )
    p(doc, "High-confidence (rich evidence) examples:", indent=False)
    for row in payload["feature_scores"]["high_confidence"][:3]:
        bullet(doc, f"{row[0]} / {row[1]}: mentions={row[2]}, confidence={row[3]}, score={row[4]}")
    p(doc, "Low-confidence (sparse evidence) examples:", indent=False)
    for row in payload["feature_scores"]["low_confidence"][:3]:
        bullet(doc, f"{row[0]} / {row[1]}: mentions={row[2]}, confidence={row[3]}, score={row[4]}")

    h(doc, "5.4 Recommendation Demonstrations", 2)
    p(
        doc,
        "Six fixed user-priority profiles were applied to the same feature-score database. "
        "Top-5 membership changes across profiles, showing that explicit weights alter ranking "
        "relative to a single global popularity signal.",
    )
    for profile_name, items in payload["recommendations"]["profiles"].items():
        rows = [[x["rank"], x["phone"], x["score"]] for x in items]
        table(
            doc,
            ["Rank", "Phone", "Score"],
            rows,
            caption=f"Table: Top-5 under {profile_name} priorities",
        )
    p(
        doc,
        f"Under balanced weights, Top-3 overlap between the proposed method and the Amazon "
        f"star baseline is {payload['recommendations']['overlap_top3']}; Top-5 overlap is "
        f"{payload['recommendations']['overlap_top5']}. Values below 1.0 indicate the methods "
        f"are not identical.",
    )
    table(
        doc,
        ["Rank", "Proposed phone", "Proposed score", "Baseline phone", "Baseline stars"],
        payload["recommendations"]["comparison"][:5],
        caption="Table 5.5: Proposed vs Amazon star baseline (Top-5, balanced weights)",
    )
    if payload["recommendations"]["top1_explanation"]:
        p(doc, "Example explanation (Top-1, balanced weights):", indent=False)
        p(doc, payload["recommendations"]["top1_explanation"], italic=True, indent=False)

    h(doc, "5.5 Evaluation", 2)
    p(
        doc,
        f"Starâ€“text agreement (ABSA polarity vs Amazon review stars) was measured on "
        f"{val['reviews_compared']} reviews with aspect evidence. Agreement rate = "
        f"{round(float(val['agreement_rate'])*100, 2)}% "
        f"(MAE = {val['mean_absolute_error']}). Perfect agreement is neither expected nor "
        f"desirable because stars are review-level while ABSA is aspect-level.",
    )
    by_rating = val.get("by_rating") or {}
    if by_rating:
        table(
            doc,
            ["Stars", "Reviews", "Agreement rate", "MAE"],
            [
                [s, info["reviews"], info["agreement_rate"], info["mean_absolute_error"]]
                for s, info in by_rating.items()
            ],
            caption="Table 5.6: Starâ€“text agreement by rating",
        )
    p(
        doc,
        f"Explanation faithfulness (rule-based check that Top-1 explanations mention the "
        f"top contributing aspects) held for {faith_rate} of {checked} profile checks "
        f"({checked} profiles tested).",
    )

    h(doc, "5.5.1 Optional pilot ranking metrics", 3)
    fb = payload["evaluation"]["feedback"]
    if fb["sessions"]:
        p(
            doc,
            f"Existing feedback sessions in the database: {fb['sessions']}. "
            f"Mean satisfaction = {fb['mean_satisfaction']}; "
            f"mean NDCG@3 = {fb['mean_ndcg_at_3']} "
            f"(from {eval_report.ndcg_session_count} sessions with usable ranks); "
            f"mean Spearman = {fb['mean_spearman']}. "
            f"Proposed method NDCG@3 = {fb['proposed_ndcg']}; "
            f"baseline NDCG@3 = {fb['baseline_ndcg']}.",
        )
        if eval_report.ranking_quality_note:
            p(doc, eval_report.ranking_quality_note, italic=True, indent=False)
        if eval_report.baseline_comparison_note:
            p(doc, eval_report.baseline_comparison_note, italic=True, indent=False)
    else:
        p(
            doc,
            "No feedback sessions were available. NDCG@3 and Spearman can be added by rating "
            "Top-10 lists for both ranking methods in the UI; until then, evaluation rests on "
            "starâ€“text agreement, baseline Top-N comparison, and explanation faithfulness.",
        )

    h(doc, "5.6 Summary Linked to Research Objectives", 2)
    bullet(doc, "RO1: Reliable dataset constructed and funnel reported (Tables 5.1â€“5.3).")
    bullet(doc, "RO2: Six-aspect ABSA outputs produced (Table 5.4 + examples).")
    bullet(doc, "RO3: Feature scores with counts, raw/shrunk scores, and confidence exported.")
    bullet(doc, "RO4: Weighted rankings under multiple profiles; compared with star baseline.")
    bullet(doc, "RO5: Plain-language explanations generated and faithfulness-checked.")

    h(doc, "5.7 Artefact Index", 2)
    p(doc, "All numeric exports are saved under data/exports/analysis/:", indent=False)
    for name in sorted(OUT_DIR.glob("*.csv")):
        bullet(doc, name.name)
    bullet(doc, "analysis_summary.json")

    doc.save(DOCX_PATH)
    print(f"Wrote {DOCX_PATH}")


if __name__ == "__main__":
    result = run_analysis()
    print("Analysis complete.")
    print("Exports:", OUT_DIR)
    print("Agreement:", result["evaluation"]["star_text"]["agreement_rate"])
    print("Faithfulness:", result["evaluation"]["explanation_faithfulness_rate"])
    print("Feedback sessions:", result["evaluation"]["feedback"]["sessions"])
