"""Generate full research thesis Word document (as-built implementation)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUT = Path(__file__).resolve().parents[2] / "Thesis_IM2021049_Smartphone_ABSA_Recommendation.docx"


def set_run_font(run, *, bold=False, italic=False, size=12, name="Times New Roman"):
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    run.font.name = name
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:ascii"), name)
    rFonts.set(qn("w:hAnsi"), name)
    rFonts.set(qn("w:cs"), name)


def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        set_run_font(run, bold=True, size=16 if level == 1 else (14 if level == 2 else 12))
    return h


def add_para(doc, text, *, bold=False, italic=False, size=12, space_after=8, first_line=True):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if first_line:
        pf.first_line_indent = Inches(0.5)
    run = p.add_run(text)
    set_run_font(run, bold=bold, italic=italic, size=size)
    return p


def add_bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet")
    p.clear()
    p.paragraph_format.left_indent = Inches(0.25 + 0.25 * level)
    p.paragraph_format.first_line_indent = Inches(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    run = p.add_run(text)
    set_run_font(run, size=12)
    return p


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ""
        run = cell.paragraphs[0].add_run(h)
        set_run_font(run, bold=True, size=11)
    for r_i, row in enumerate(rows):
        for c_i, val in enumerate(row):
            cell = table.rows[r_i + 1].cells[c_i]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            set_run_font(run, size=11)
    doc.add_paragraph()
    return table


def page_break(doc):
    doc.add_page_break()


def build():
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1.25)
    section.right_margin = Inches(1)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    style._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    style._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")

    # ---------- TITLE PAGE ----------
    for _ in range(2):
        doc.add_paragraph()
    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run(
        "EXPLAINABLE FEATURE-BASED SMARTPHONE RECOMMENDATION "
        "USING ASPECT-BASED SENTIMENT ANALYSIS OF AMAZON USER REVIEWS"
    )
    set_run_font(r, bold=True, size=16)

    for line in [
        "",
        "A Research Thesis Submitted in Partial Fulfilment of the Requirements",
        "for the Degree of Bachelor of Science",
        "Department of Industrial Management",
        "Faculty of Science",
        "University of Kelaniya",
        "",
        "Student Registration Number: IM/2021/049",
        f"Date: {date.today().strftime('%B %Y')}",
        "",
        "Supervisor: Mr. Dinesh Asanka",
        "",
        "Note: This document describes the system AS BUILT. Quantitative evaluation "
        "metrics that depend on your final user-study sessions should be filled from "
        "the Evaluation tab before final submission.",
    ]:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Inches(0)
        run = p.add_run(line)
        set_run_font(run, size=12, italic=("Note:" in line))

    page_break(doc)

    # ---------- ABSTRACT ----------
    add_heading(doc, "Abstract", 1)
    add_para(
        doc,
        "Selecting a smartphone is a multi-criteria decision. Buyers must trade off "
        "battery life, camera quality, display, performance, design, and price or value "
        "for money. Traditional e-commerce interfaces emphasise aggregate star ratings and "
        "popularity, which hide feature-level opinions expressed in textual reviews. "
        "This research develops an explainable, feature-based smartphone recommendation "
        "prototype that analyses Amazon review text with Aspect-Based Sentiment Analysis "
        "(ABSA), aggregates opinions into per-feature performance scores, and ranks "
        "handsets according to user-defined feature priorities.",
        first_line=True,
    )
    add_para(
        doc,
        "The implemented system uses a Python research stack comprising FastAPI, SQLite, "
        "SQLAlchemy, and a custom web interface. The primary ABSA engine is a domain "
        "lexicon for offline, reproducible annotation; an optional OpenAI-compatible large "
        "language model (LLM) API is supported but was not required for the core "
        "experiments. Local fine-tuning of transformer models such as BERT was not "
        "performed. The pipeline covers preprocessing, sentence segmentation, aspect and "
        "sentiment extraction, score aggregation with Bayesian shrinkage, weighted "
        "recommendation with plain-language explanations, and comparison against an "
        "Amazon star-rating baseline.",
        first_line=True,
    )
    add_para(
        doc,
        "The final analysis corpus contains 224 smartphone products and 3,389 English "
        "reviews retained after preprocessing (from 4,092 raw CSV rows and 227 ASINs). "
        "Segmentation produced 31,685 sentences and ABSA produced 13,914 aspect–sentiment "
        "records. Feature scores were computed for 221 phones across six aspects: "
        "battery, camera, display, performance, design, and price. Evaluation uses "
        "user-assigned 1–5 ratings to compute NDCG@3 and Spearman rank correlation, "
        "compares the proposed method with the star baseline, and reports agreement "
        "between review-text polarity and star ratings as a sanity check. Manual gold "
        "labels for Macro-F1 were treated as optional and were not required for the "
        "primary evaluation path.",
        first_line=True,
    )
    add_para(
        doc,
        "Keywords: Aspect-Based Sentiment Analysis; smartphone recommendation; "
        "explainable AI; feature scoring; Amazon reviews; NDCG; lexicon-based NLP.",
        first_line=False,
        italic=True,
    )

    page_break(doc)

    # ---------- ACKNOWLEDGEMENTS ----------
    add_heading(doc, "Acknowledgements", 1)
    add_para(
        doc,
        "I sincerely thank my research supervisor, Mr. Dinesh Asanka, for guidance, "
        "constructive feedback, and continuous support throughout this research. I also "
        "thank the academic and non-academic staff of the Department of Industrial "
        "Management, Faculty of Science, University of Kelaniya, and my family and "
        "friends for their encouragement during the completion of this work.",
    )

    page_break(doc)

    # ---------- ACRONYMS ----------
    add_heading(doc, "List of Acronyms", 1)
    acronyms = [
        ("ABSA", "Aspect-Based Sentiment Analysis"),
        ("API", "Application Programming Interface"),
        ("ASIN", "Amazon Standard Identification Number"),
        ("CLI", "Command-Line Interface"),
        ("CSV", "Comma-Separated Values"),
        ("LLM", "Large Language Model"),
        ("NDCG", "Normalized Discounted Cumulative Gain"),
        ("NLP", "Natural Language Processing"),
        ("ORM", "Object-Relational Mapping"),
        ("REST", "Representational State Transfer"),
        ("SQLite", "Embedded relational database used for the research prototype"),
        ("UI", "User Interface"),
    ]
    add_table(doc, ["Acronym", "Meaning"], acronyms)

    page_break(doc)

    # ---------- CHAPTER 1 ----------
    add_heading(doc, "Chapter 1: Introduction", 1)
    add_heading(doc, "1.1 Background of the Study", 2)
    add_para(
        doc,
        "Online marketplaces publish large volumes of user-generated reviews. For "
        "smartphones, these reviews discuss technical and experiential attributes that "
        "matter differently to different buyers. A photography-oriented user may prioritise "
        "camera and display, whereas a commuting user may prioritise battery and "
        "performance. Aggregate star ratings compress these multi-aspect opinions into a "
        "single number and therefore cannot directly support priority-driven choice.",
    )
    add_para(
        doc,
        "Aspect-Based Sentiment Analysis separates opinions by product feature and classifies "
        "each mention as positive, negative, or neutral. When aspect signals are aggregated "
        "into feature scores and combined with explicit user weights, the resulting ranking "
        "can be explained in terms of the same features the user declared important. This "
        "study builds and evaluates a research prototype that operationalises that idea for "
        "smartphone recommendation.",
    )

    add_heading(doc, "1.2 Research Problem", 2)
    add_para(
        doc,
        "The research problem is the lack of an accessible, transparent recommendation "
        "mechanism that (i) extracts feature-level sentiment from smartphone reviews, "
        "(ii) converts those opinions into comparable feature scores, (iii) ranks phones "
        "according to user priorities, and (iv) explains each recommendation using the "
        "underlying evidence rather than opaque popularity signals alone.",
    )

    add_heading(doc, "1.3 Research Aim", 2)
    add_para(
        doc,
        "To develop an explainable feature-based smartphone recommendation system using "
        "Aspect-Based Sentiment Analysis (ABSA) of user reviews. The system analyses "
        "textual reviews, extracts feature-level sentiments, computes feature performance "
        "scores, and generates transparent, requirement-driven recommendations without "
        "relying on collaborative user history.",
    )

    add_heading(doc, "1.4 Research Objectives", 2)
    for o in [
        "To collect and prepare a structured dataset of smartphone reviews from Amazon for natural language processing and analysis.",
        "To identify predefined smartphone features from review text and classify the sentiment associated with each feature as positive, negative, or neutral using ABSA.",
        "To determine each smartphone’s feature performance score by aggregating sentiment mentions for each feature.",
        "To develop a recommendation engine that ranks smartphones using weighted feature scores based on user-defined feature preferences.",
        "To produce plain-language explanation messages that support each suggestion using the actual feature scores.",
    ]:
        add_bullet(doc, o)

    add_heading(doc, "1.5 Research Questions", 2)
    for q in [
        "How can sentiment at the feature level be extracted from smartphone reviews in a reproducible research prototype?",
        "How can feature-level sentiments be combined into useful performance scores for ranking?",
        "How can explainable recommendations be produced using feature scores and user priorities?",
        "How does the proposed ranking compare with a basic Amazon star-rating baseline under user-centred evaluation?",
    ]:
        add_bullet(doc, q)

    add_heading(doc, "1.6 Scope and Delimitations", 2)
    add_para(
        doc,
        "The study is limited to a research prototype for English-language Amazon "
        "smartphone reviews. Recommendation does not use collaborative filtering and does "
        "not scrape live pages at query time. The primary ABSA technique is a domain "
        "lexicon; optional LLM API annotation is available but is not treated as a "
        "trained BERT model. Gold-label Macro-F1 evaluation is optional and was not "
        "required for the primary evaluation path used in this report.",
    )

    add_heading(doc, "1.7 Significance", 2)
    add_para(
        doc,
        "The work contributes a complete, auditable pipeline from reviews to explained "
        "rankings, suitable for dissertation demonstration and for discussing the "
        "managerial value of feature-aware decision support in e-commerce settings.",
    )

    add_heading(doc, "1.8 Organisation of the Thesis", 2)
    add_para(
        doc,
        "Chapter 2 reviews related literature. Chapter 3 presents methodology. Chapter 4 "
        "describes system design and implementation techniques. Chapter 5 reports dataset "
        "and evaluation results. Chapter 6 discusses findings. Chapter 7 concludes and "
        "outlines future work.",
    )

    page_break(doc)

    # ---------- CHAPTER 2 ----------
    add_heading(doc, "Chapter 2: Literature Review", 1)
    add_heading(doc, "2.1 Recommendation Systems", 2)
    add_para(
        doc,
        "Classical recommender systems rely on collaborative filtering, content features, "
        "or hybrid models. Collaborative methods suffer from cold start when user–item "
        "interaction histories are thin. Content and multi-criteria approaches are more "
        "suitable when products are described by attributes and when new users can state "
        "preferences explicitly. This study adopts an explicit preference-weighting design "
        "rather than latent collaborative profiles.",
    )

    add_heading(doc, "2.2 Reviews and Product Evaluation", 2)
    add_para(
        doc,
        "Online reviews contain rich qualitative evidence beyond star ratings. Prior work "
        "shows that buyers attend to specific attributes and that overall ratings can "
        "disagree with aspect-level praise or criticism. Review mining therefore supports "
        "finer product comparison, provided spam, language noise, and duplicates are controlled.",
    )

    add_heading(doc, "2.3 Aspect-Based Sentiment Analysis", 2)
    add_para(
        doc,
        "ABSA comprises aspect identification and aspect-level sentiment classification. "
        "Approaches range from lexicon and rule-based systems, through classical machine "
        "learning, to neural and transformer models such as BERT. Lexicon methods are "
        "interpretable and require no labelled training set. Transformer models often "
        "achieve higher contextual accuracy but demand labelled data, compute, and careful "
        "domain adaptation. This research deliberately implements a lexicon-first ABSA "
        "engine for reproducibility and optionally supports an LLM API, without claiming "
        "a fine-tuned BERT deployment.",
    )

    add_heading(doc, "2.4 Explainable Recommendation", 2)
    add_para(
        doc,
        "Explainability improves trust when recommendations affect purchase decisions. "
        "Feature-score explanations that cite the user’s priorities and the product’s "
        "review-derived scores are more actionable than generic popularity statements. "
        "The prototype therefore generates plain-language “why recommended” text from the "
        "same scores used in ranking.",
    )

    add_heading(doc, "2.5 Research Gap", 2)
    add_para(
        doc,
        "Many ABSA studies stop at classification metrics, while many recommenders optimise "
        "rating prediction without transparent feature evidence. Fewer systems integrate "
        "Amazon smartphone review ABSA, explicit user weights, auditable score aggregation, "
        "plain-language explanations, and a star-rating baseline comparison in one "
        "prototype. That integration gap motivates the present design-and-development study.",
    )

    add_heading(doc, "2.6 Conceptual Framework", 2)
    add_para(
        doc,
        "Reviews → preprocessing and segmentation → ABSA (aspect + sentiment) → feature "
        "score database → user priority weights → ranked Top-N with explanations → "
        "evaluation against user ratings and Amazon star baseline.",
    )

    page_break(doc)

    # ---------- CHAPTER 3 ----------
    add_heading(doc, "Chapter 3: Methodology", 1)
    add_heading(doc, "3.1 Research Design", 2)
    add_para(
        doc,
        "The study follows a design-science / prototype development approach. A working "
        "software artefact was constructed to satisfy the five research objectives and "
        "evaluated using corpus statistics, baseline comparison, and user-centred ranking "
        "metrics. The analytical unit is the aspect-level clause or sentence mention; the "
        "aggregation unit is the smartphone product.",
    )

    add_heading(doc, "3.2 Data Collection", 2)
    add_para(
        doc,
        "The primary corpus is an offline Amazon smartphone review file "
        "(data/full_reviews.csv) containing product identifiers (ASIN), titles, prices, "
        "ratings, and review text. Non-phone listings such as user manuals were removed "
        "before analysis. Optional alternative paths include Playwright-based live scraping "
        "and Hugging Face Amazon Reviews 2023 ingest; these are supporting options, not "
        "required at recommendation time.",
    )

    add_heading(doc, "3.3 Dataset Funnel (Verified Counts)", 2)
    add_para(doc, "Table 3.1 summarises the corpus after each preparation stage.", first_line=False)
    add_table(
        doc,
        ["Stage", "Unit", "Count"],
        [
            ["Raw CSV", "Review rows / unique ASINs", "4,092 / 227"],
            ["After dropping manuals/guides", "Review rows / ASINs", "4,080 / 224"],
            ["Loaded into SQLite", "Phones / reviews", "224 / 4,080"],
            ["After Step 1 preprocessing (kept)", "Reviews", "3,389"],
            ["Excluded in Step 1", "Reviews", "691"],
            ["Step 2 sentence segmentation", "Sentences", "31,685"],
            ["Steps 3–4 ABSA output", "Aspect–sentiment records", "13,914"],
            ["Step 6 feature scores", "Phones with scores", "221"],
        ],
    )
    add_para(doc, "Breakdown of the 691 excluded reviews:", first_line=False)
    add_table(
        doc,
        ["Exclusion reason", "Count"],
        [
            ["language_filtered (non-English)", "663"],
            ["all_caps", "12"],
            ["no_alpha_content", "10"],
            ["too_short", "3"],
            ["generic_only", "3"],
        ],
    )
    add_para(
        doc,
        "Kept reviews per phone after preprocessing ranged from 1 to 24 (mean approximately "
        "15.2 across 223 phones with at least one kept review). Average sentences per "
        "processed kept review were approximately 9.35.",
    )

    add_heading(doc, "3.4 Preprocessing (Step 1)", 2)
    add_para(
        doc,
        "Technique: rule-based text cleaning implemented in app/nlp/preprocess.py. "
        "Operations include HTML stripping, Unicode normalisation, artefact removal, "
        "whitespace collapse, de-duplication via content hashing, spam heuristics "
        "(extreme shortness, all-caps, low alphabetic ratio, generic-only text), and "
        "English language detection using langdetect. Only English reviews remain in the "
        "main analysis path.",
    )

    add_heading(doc, "3.5 Sentence Segmentation (Step 2)", 2)
    add_para(
        doc,
        "Technique: pysbd sentence boundary detection with fallbacks for short fragments. "
        "Segmentation isolates feature opinions that co-occur in multi-clause reviews "
        "(for example, praise for camera and criticism of battery).",
    )

    add_heading(doc, "3.6 ABSA Techniques (Steps 3–4)", 2)
    add_para(
        doc,
        "Closed aspect taxonomy (core set): battery, camera, display, performance, design, "
        "and price (value-for-money language in reviews). Sentiment labels: positive, "
        "negative, neutral.",
    )
    add_para(
        doc,
        "Primary technique — Domain lexicon engine: keyword and phrase matching per aspect, "
        "polarity lexicon with negation windows, intensifiers/diminishers, and contrast "
        "markers (for example, “but”) so sentiment does not incorrectly leak across clauses. "
        "This engine runs fully offline and is the recommended reproducible thesis engine "
        "(python run.py analyze --force --engine lexicon).",
    )
    add_para(
        doc,
        "Optional technique — LLM API engine: batched JSON annotation via httpx against an "
        "OpenAI-compatible chat endpoint. Mode ABSA_ENGINE=auto selects LLM when an API key "
        "is present and otherwise falls back to lexicon. Failed LLM batches degrade to "
        "lexicon and are marked as lexicon_fallback in stored rows. This study does not "
        "train or fine-tune BERT locally.",
    )

    add_heading(doc, "3.7 Feature Score Aggregation (Step 6)", 2)
    add_para(
        doc,
        "For each (phone, aspect): raw_score = (positive + 0.5 × neutral) / mentions. "
        "Stored score applies Bayesian shrinkage toward the corpus mean with strength "
        "k = SHRINKAGE_STRENGTH (default 5): score = (mentions × raw_score + k × mean) / "
        "(mentions + k). Sparse aspects are therefore not over-trusted. Minimum mention "
        "thresholds flag low-confidence scores.",
    )

    add_heading(doc, "3.8 Recommendation Method", 2)
    add_para(
        doc,
        "Users assign importance marks from 0–10 for each of the six aspects. Weights are "
        "normalised. Final score = Σ(wₐ × scoreₐ) / Σ(wₐ). Missing aspects are imputed with "
        "the candidate-set mean and flagged as imputed (never forced to zero). Coverage "
        "reports the share of requested weight backed by real mentions. Optional min/max "
        "USD filters constrain list price. A baseline method ranks by Amazon site_rating "
        "only. Explanations cite the strongest matching aspects under the user’s weights.",
    )

    add_heading(doc, "3.9 Evaluation Methods", 2)
    add_bullet(doc, "User 1–5 ratings after viewing a ranked list (relevance / satisfaction).")
    add_bullet(doc, "NDCG@3 computed from those graded ratings.")
    add_bullet(doc, "Spearman rank correlation between system order and user ratings.")
    add_bullet(doc, "Comparison of sessions tagged weighted (proposed) versus star_rating (baseline).")
    add_bullet(doc, "Star–text agreement: consistency between review polarity and Amazon stars as an ABSA sanity check.")
    add_bullet(doc, "Gold-label Macro-F1: optional CLI path; not required for the primary results narrative.")

    add_heading(doc, "3.10 Tools and Technologies", 2)
    add_table(
        doc,
        ["Layer", "Technologies"],
        [
            ["Language", "Python 3.12+"],
            ["API / server", "FastAPI, Uvicorn, Pydantic"],
            ["Database", "SQLite, SQLAlchemy 2.0"],
            ["Data handling", "Pandas"],
            ["NLP", "pysbd, langdetect, domain lexicon; httpx for optional LLM"],
            ["Scraping (optional)", "Playwright, BeautifulSoup4, lxml, Tenacity"],
            ["CLI", "Typer, Rich"],
            ["UI", "HTML/CSS/JS static research UI; Streamlit optional"],
            ["Config", "python-dotenv / pydantic-settings"],
        ],
    )

    page_break(doc)

    # ---------- CHAPTER 4 ----------
    add_heading(doc, "Chapter 4: System Design and Implementation", 1)
    add_heading(doc, "4.1 Functional Requirements", 2)
    for item in [
        "Ingest offline review corpora into a structured database.",
        "Run Steps 1–6 of the ABSA pipeline and store intermediate artefacts.",
        "Expose feature scores and phone metadata through a REST API.",
        "Rank phones by user weights or by Amazon star baseline.",
        "Generate plain-language explanations.",
        "Collect user ratings and produce an evaluation report.",
        "Provide a research UI for demonstration and user study.",
    ]:
        add_bullet(doc, item)

    add_heading(doc, "4.2 Architecture", 2)
    add_para(
        doc,
        "The architecture is layered. The data layer stores phones, reviews, sentences, "
        "aspect sentiments, aspect scores, prices, jobs, and recommendation feedback in "
        "SQLite. The NLP layer implements preprocessing, segmentation, ABSA, and "
        "aggregation. The service layer implements analysis orchestration, recommendation, "
        "feedback aggregation, and corpus import. The API layer (FastAPI) exposes REST "
        "endpoints and serves the static UI at /ui/. A Typer CLI (run.py) supports batch "
        "research workflows without the browser.",
    )

    add_heading(doc, "4.3 Database Design", 2)
    add_para(
        doc,
        "Principal tables: smartphones, reviews, sentences, aspect_sentiments, "
        "aspect_scores, price_observations, jobs, recommendation_feedback. Relationships "
        "are maintained through foreign keys (for example, review → sentences → aspect "
        "sentiments; phone → aspect scores). This design preserves provenance from raw "
        "review text to final feature scores.",
    )

    add_heading(doc, "4.4 Implementation of the NLP Pipeline", 2)
    add_para(
        doc,
        "Module map: app/nlp/preprocess.py (Step 1), segment.py (Step 2), absa.py and "
        "aspects.py (Steps 3–4), aggregate.py (Step 6). Analysis orchestration lives in "
        "app/services/analysis.py. CSV ingest is implemented in "
        "app/services/scraped_csv_ingest.py. Aspect keywords and polarity lexicons are "
        "centralised so that both lexicon and LLM paths share the same closed label set.",
    )

    add_heading(doc, "4.5 Recommendation and Explanation Implementation", 2)
    add_para(
        doc,
        "app/services/recommender.py builds feature vectors, applies filters, normalises "
        "weights, imputes missing aspects, and returns ranked Recommendation objects with "
        "breakdown and coverage. build_explanation() produces human-readable text for "
        "weighted and baseline methods. Ranking method is stored with feedback so "
        "Evaluation can compare proposed versus baseline sessions.",
    )

    add_heading(doc, "4.6 API and CLI", 2)
    add_para(
        doc,
        "Key endpoints include GET /health, /stats, /aspects, /phones, /features; "
        "POST /recommend; POST /feedback; GET /feedback/evaluation; POST /analyze and "
        "/scrape (background jobs); GET /jobs/{id}. CLI commands include prepare-csv, "
        "analyze, serve, stats, features, recommend, export, website, and optional "
        "sample-gold / evaluate-absa.",
    )

    add_heading(doc, "4.7 User Interface", 2)
    add_para(
        doc,
        "The primary UI (app/static) provides Recommend, Phones, and Evaluation views. "
        "Recommend supports priority presets, six aspect sliders (including Design), "
        "budget filters, ranking-method toggle, Top-10 results with explanations, and "
        "per-phone 1–5 ratings. Phones shows aspect score bars. Evaluation shows "
        "cumulative satisfaction, NDCG@3, Spearman, method comparison, and star–text "
        "agreement. Visual design uses Outfit and IBM Plex Mono with a teal/slate theme "
        "and light/dark modes. An optional Streamlit staged website maps one page to each "
        "methodology stage.",
    )

    add_heading(doc, "4.8 Configuration", 2)
    add_para(
        doc,
        "Runtime behaviour is controlled by .env (see .env.example): ABSA_ENGINE, "
        "ASPECT_SET=core, LLM settings, LANGUAGE_FILTER=en, NEUTRAL_WEIGHT, "
        "MIN_MENTIONS_FOR_SCORE, SHRINKAGE_STRENGTH, and scraping politeness parameters.",
    )

    add_heading(doc, "4.9 Mapping Objectives to Implementation", 2)
    add_table(
        doc,
        ["Objective", "Implementation"],
        [
            ["1 Data collection & preparation", "CSV/scrape/HF ingest + preprocess"],
            ["2 ABSA aspect + sentiment", "Lexicon ABSA (+ optional LLM)"],
            ["3 Feature scores", "aggregate.py → aspect_scores"],
            ["4 Weighted ranking", "recommender.py + Recommend UI"],
            ["5 Explanations", "build_explanation() on each result"],
        ],
    )

    page_break(doc)

    # ---------- CHAPTER 5 ----------
    add_heading(doc, "Chapter 5: Results and Evaluation", 1)
    add_heading(doc, "5.1 Corpus Preparation Results", 2)
    add_para(
        doc,
        "The verified funnel in Section 3.3 is the quantitative backbone of the data "
        "chapter. Starting from 4,092 raw rows (227 ASINs), 12 manual/guide listings were "
        "removed, leaving 4,080 rows and 224 phones. Preprocessing retained 3,389 English "
        "usable reviews and excluded 691 rows, predominantly for language filtering (663). "
        "The final analytical review set is therefore n = 3,389 reviews on 224 phones, "
        "with feature scores available for 221 phones.",
    )

    add_heading(doc, "5.2 ABSA Output Distribution", 2)
    add_para(doc, "Table 5.1 reports aspect mention counts in the final ABSA table.", first_line=False)
    add_table(
        doc,
        ["Aspect", "Mention count"],
        [
            ["battery", "4,479"],
            ["display", "2,450"],
            ["price", "2,313"],
            ["camera", "2,019"],
            ["performance", "1,403"],
            ["design", "1,250"],
            ["Total", "13,914"],
        ],
    )
    add_para(doc, "Table 5.2 reports overall sentiment label counts.", first_line=False)
    add_table(
        doc,
        ["Sentiment", "Count"],
        [
            ["positive", "6,736"],
            ["neutral", "5,744"],
            ["negative", "1,434"],
            ["Total", "13,914"],
        ],
    )
    add_para(
        doc,
        "Battery is the most frequently discussed aspect in this corpus, followed by "
        "display and price. Design is present with 1,250 mentions and scores on 200 "
        "phones with at least one design mention, confirming that the sixth core feature "
        "is operational after lexicon re-analysis.",
    )

    add_heading(doc, "5.3 Recommendation Behaviour", 2)
    add_para(
        doc,
        "Changing user priorities alters Top-10 membership and order, which is expected "
        "for a feature-weighted method. The Amazon star baseline produces a different "
        "ordering driven by site_rating rather than aspect scores. Explanations for the "
        "proposed method cite the highest-contribution aspects under the active weights; "
        "baseline explanations state that ranking used Amazon stars only.",
    )

    add_heading(doc, "5.4 User-Centred Ranking Metrics", 2)
    add_para(
        doc,
        "After each ranking run, participants (or the researcher during pilot tests) rate "
        "phones from 1 to 5. Those ratings serve as graded relevance for NDCG@3 and for "
        "Spearman correlation. Sessions are tagged by ranking_method so Evaluation can "
        "compare proposed versus baseline performance.",
    )
    add_para(
        doc,
        "[FILL BEFORE FINAL BINDING — copy from Evaluation tab after your complete user "
        "study] Mean NDCG@3 (proposed): ____ ; Mean NDCG@3 (star baseline): ____ ; "
        "Mean Spearman (proposed): ____ ; Mean Spearman (baseline): ____ ; Number of "
        "rated sessions: ____ .",
        italic=True,
        first_line=False,
    )

    add_heading(doc, "5.5 Star–Text Agreement", 2)
    add_para(
        doc,
        "As a lightweight ABSA sanity check, review-level polarity summarised from aspect "
        "sentiments is compared with Amazon star ratings. Perfect agreement is neither "
        "expected nor desirable because a high-star review may still criticise one feature. "
        "Report the agreement rate shown on the Evaluation tab here: ____%.",
    )

    add_heading(doc, "5.6 Achievement Against Objectives", 2)
    add_para(
        doc,
        "All five objectives are realised in the working prototype: a prepared corpus, "
        "ABSA annotations, feature scores, weighted ranking, and explanations. Evaluation "
        "infrastructure for NDCG@3, Spearman, baseline comparison, and star–text agreement "
        "is implemented in the Evaluation view.",
    )

    page_break(doc)

    # ---------- CHAPTER 6 ----------
    add_heading(doc, "Chapter 6: Discussion", 1)
    add_heading(doc, "6.1 Interpretation of Techniques", 2)
    add_para(
        doc,
        "The lexicon ABSA engine provides transparent mappings from words and phrases to "
        "aspects and polarities. This transparency supports dissertation defence: every "
        "score can be traced to stored sentences and aspect_sentiment rows. The trade-off "
        "is weaker handling of sarcasm, highly implicit opinions, and novel slang. An "
        "optional LLM path can improve contextual reading when an API key and quota are "
        "available, but it introduces cost, rate limits, and reduced offline reproducibility.",
    )

    add_heading(doc, "6.2 Proposed Ranking versus Star Baseline", 2)
    add_para(
        doc,
        "Star ratings reflect global satisfaction and popularity. Feature-weighted ranking "
        "reflects the user’s declared trade-offs. Divergence between the two lists is "
        "therefore informative rather than automatically an error: a highly rated phone "
        "may still score poorly on a feature the user marked as critical. The dual-method "
        "UI enables that comparison experimentally.",
    )

    add_heading(doc, "6.3 Explainability", 2)
    add_para(
        doc,
        "Explanations are faithful to the ranking inputs because they are generated from "
        "the same weighted aspect contributions. Coverage and imputation flags communicate "
        "uncertainty when review evidence is thin—an important honesty property for "
        "decision-support systems.",
    )

    add_heading(doc, "6.4 As-Built versus Proposal Wording", 2)
    add_table(
        doc,
        ["Proposal emphasis", "As-built delivery"],
        [
            ["Transformer / BERT training", "Lexicon ABSA + optional LLM API"],
            ["Six features including design", "Implemented in core aspect set"],
            ["Gold Macro-F1 labelling", "Optional / not primary"],
            ["Rating baseline comparison", "Implemented (star_rating method)"],
            ["Plain-language explanations", "Implemented"],
        ],
    )

    add_heading(doc, "6.5 Limitations", 2)
    add_bullet(doc, "Corpus limited to one marketplace and English text.")
    add_bullet(doc, "Review counts per phone are modest (often ≤ 24 kept reviews).")
    add_bullet(doc, "Lexicon coverage is finite.")
    add_bullet(doc, "User-study statistical power depends on the number of completed rating sessions.")
    add_bullet(doc, "List prices and review value language are related but not identical signals.")

    page_break(doc)

    # ---------- CHAPTER 7 ----------
    add_heading(doc, "Chapter 7: Conclusion and Future Work", 1)
    add_heading(doc, "7.1 Conclusion", 2)
    add_para(
        doc,
        "This research delivered an explainable feature-based smartphone recommendation "
        "prototype driven by ABSA of Amazon reviews. Using a lexicon-centred NLP pipeline "
        "on a cleaned corpus of 3,389 reviews, the system computed six-aspect scores for "
        "221 phones, ranked handsets by user priorities, explained recommendations in "
        "plain language, and supported evaluation against an Amazon star baseline. The "
        "five approved research objectives are satisfied at prototype level.",
    )

    add_heading(doc, "7.2 Contributions", 2)
    add_bullet(doc, "End-to-end research artefact from CSV ingest to Evaluation UI.")
    add_bullet(doc, "Reproducible lexicon ABSA for smartphone aspects including design.")
    add_bullet(doc, "Auditable scoring with shrinkage, coverage, and explanations.")
    add_bullet(doc, "Comparative evaluation design versus star-rating baseline.")

    add_heading(doc, "7.3 Future Work", 2)
    add_bullet(doc, "Larger user study with pre-registered analysis of NDCG@3 and Spearman.")
    add_bullet(doc, "Optional gold annotation sample for Macro-F1 if required by examiners.")
    add_bullet(doc, "Hybrid lexicon–LLM ensembles with cost controls.")
    add_bullet(doc, "Extended aspects (software, connectivity, audio, durability).")
    add_bullet(doc, "Multilingual support and additional marketplaces under ethics approval.")
    add_bullet(doc, "Richer faithfulness checks linking explanations to highlighted review spans.")

    add_heading(doc, "7.4 Final Remarks", 2)
    add_para(
        doc,
        "Feature-aware recommendation from review text is feasible without collaborative "
        "filtering and without mandatory BERT fine-tuning, provided the pipeline, scores, "
        "and explanations remain transparent and the evaluation honestly documents "
        "as-built techniques and corpus limits.",
    )

    page_break(doc)

    # ---------- REFERENCES (starter) ----------
    add_heading(doc, "References", 1)
    add_para(
        doc,
        "Complete the reference list using your approved proposal bibliography and any "
        "additional sources cited while writing Chapters 2 and 6. Below are placeholder "
        "entries illustrating the expected style; replace with your exact citations.",
        italic=True,
        first_line=False,
    )
    refs = [
        "Liu, B. (2012). Sentiment Analysis and Opinion Mining. Morgan & Claypool.",
        "Musto, C., et al. (2017). Related work on aspect-aware and review-aware recommendation systems.",
        "Pontiki, M., et al. SemEval ABSA shared tasks — foundational ABSA evaluation practice.",
        "Järvelin, K., & Kekäläinen, J. (2002). Cumulated gain-based evaluation of IR techniques. ACM TOIS.",
        "Amazon customer reviews / McAuley Lab Amazon Reviews resources as applicable to your data path.",
        "Your approved proposal: Research Proposal IM/2021/049.",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Inches(-0.5)
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run(ref)
        set_run_font(run, size=12)

    page_break(doc)

    # ---------- APPENDICES ----------
    add_heading(doc, "Appendix A: Recommended Demo Script", 1)
    add_bullet(doc, "Show Phones tab with six aspect bars including Design.")
    add_bullet(doc, "Set priorities (for example, camera-heavy) and Rank with proposed method.")
    add_bullet(doc, "Read the Top-1 explanation aloud.")
    add_bullet(doc, "Switch to Amazon stars, Rank again, and rate both lists.")
    add_bullet(doc, "Open Evaluation and discuss NDCG / method comparison / star–text agreement.")

    add_heading(doc, "Appendix B: Key Commands", 1)
    add_para(doc, "python run.py prepare-csv", first_line=False, italic=True)
    add_para(doc, "python run.py analyze --force --engine lexicon", first_line=False, italic=True)
    add_para(doc, "python run.py serve", first_line=False, italic=True)
    add_para(doc, "UI: http://127.0.0.1:8000/ui/   API docs: http://127.0.0.1:8000/docs", first_line=False)

    add_heading(doc, "Appendix C: Screenshots Checklist", 1)
    add_bullet(doc, "Recommend priorities panel (six aspects).")
    add_bullet(doc, "Top-10 results with explanation.")
    add_bullet(doc, "Phone detail drawer with aspect breakdown.")
    add_bullet(doc, "Evaluation tab summary cards.")
    add_para(
        doc,
        "Insert screenshots manually into this appendix before printing.",
        italic=True,
        first_line=False,
    )

    add_heading(doc, "Appendix D: How to Finalise Numbers", 1)
    add_para(
        doc,
        "1) Complete rating sessions for both ranking methods. 2) Open Evaluation. "
        "3) Copy NDCG@3, Spearman, agreement %, and session counts into Section 5.4–5.5. "
        "4) Update Abstract if those figures change. 5) Expand References from your "
        "proposal PDF. 6) Add screenshots to Appendix C.",
        first_line=False,
    )

    doc.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
