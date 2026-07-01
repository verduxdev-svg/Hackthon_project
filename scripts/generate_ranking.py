#!/usr/bin/env python3
"""
Hackathon Submission Script: Generate Ranked Candidates Output

This standalone script runs the full AI Recruiter pipeline and produces
the ranked_candidates_output.csv file required for hackathon submission.

Usage:
    python scripts/generate_ranking.py --jd path/to/job_description.docx
    python scripts/generate_ranking.py --jd path/to/job_description.txt
    python scripts/generate_ranking.py  # Uses sample JD if no file given

Output:
    output/ranked_candidates_output.csv
"""

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path

# ── Add project root to path ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.core.config import get_settings
from app.services.extraction_service import JDExtractionService
from app.services.ranking_service import CandidateRankingService
from app.services.candidate_loader import CandidateLoaderService
from app.models.ranking_models import Candidate


SAMPLE_JD = """
Senior AI Engineer — Talent Intelligence Platform

We are building an AI-native talent intelligence platform that matches candidates
to roles the way a great recruiter would — not by keywords, but by understanding
who actually fits.

You will own the intelligence layer: the ranking, retrieval, and matching systems
that power our platform.

What you will do:
- Build and ship an improved v2 ranking system using embeddings and hybrid retrieval
  within the first 8 weeks
- Establish evaluation infrastructure (NDCG, MRR metrics) for ongoing measurement
- Integrate LLMs for structured extraction and reasoning about candidates
- Mentor 2 junior engineers and establish code review culture

Must have:
- 5-9 years of hands-on ML engineering experience
- Python (expert level)
- Embeddings-based retrieval systems
- Vector databases (Pinecone, Weaviate, or FAISS)
- Evaluation frameworks (NDCG, MRR, precision@k)
- Production ML deployment experience

Nice to have:
- LoRA/QLoRA fine-tuning experience
- Learning-to-rank algorithms
- Open-source contributions
- HR-tech domain experience
- Distributed systems

Behavioral traits we look for:
- Bias for shipping over endless research
- Strong written communication (we are async-first)
- Comfortable with ambiguity and fast iteration
- Disagrees and commits

We do NOT want:
- Pure research backgrounds with no production deployment
- Only consulting firm experience (TCS, Infosys, Wipro, Accenture)
- Primary expertise in computer vision or speech, without NLP
- Candidates who need hand-holding on technical direction

Location: Pune, Noida, Delhi NCR, Mumbai, Hyderabad (on-site)
Notice period: Prefer ≤30 days
Company type: Product companies and startups preferred
"""


def read_jd_file(path: str) -> str:
    """Read JD from .docx or .txt file."""
    p = Path(path)
    if not p.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    if p.suffix == ".txt":
        return p.read_text(encoding="utf-8")
    elif p.suffix == ".docx":
        try:
            import docx, io
            doc = docx.Document(str(p))
            return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        except ImportError:
            print("❌ python-docx not installed. Run: pip install python-docx")
            sys.exit(1)
    else:
        print(f"❌ Unsupported file type: {p.suffix}. Use .docx or .txt")
        sys.exit(1)


def write_csv(ranked_result, output_path: str):
    """Write the ranked output to CSV in the hackathon submission format."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank",
            "candidate_id",
            "name",
            "total_score",
            "must_have_skills_score",
            "experience_score",
            "nice_to_have_score",
            "behavioral_score",
            "location_score",
            "notice_period_score",
            "disqualifier_penalty",
            "matched_must_have_skills",
            "missing_must_have_skills",
            "disqualifiers_hit",
            "recruiter_note",
        ])

        for rc in ranked_result.shortlist:
            writer.writerow([
                rc.rank,
                rc.candidate_id,
                rc.name,
                f"{rc.total_score:.2f}",
                f"{rc.score_breakdown.must_have_skills_score:.2f}",
                f"{rc.score_breakdown.experience_score:.2f}",
                f"{rc.score_breakdown.nice_to_have_score:.2f}",
                f"{rc.score_breakdown.behavioral_score:.2f}",
                f"{rc.score_breakdown.location_score:.2f}",
                f"{rc.score_breakdown.notice_period_score:.2f}",
                f"{rc.score_breakdown.disqualifier_penalty:.2f}",
                "; ".join(rc.matched_must_have_skills),
                "; ".join(rc.missing_must_have_skills),
                "; ".join(rc.disqualifiers_hit) if rc.disqualifiers_hit else "",
                rc.recruiter_note,
            ])

    print(f"\n✅ Ranked output written to: {output_path}")


async def run_pipeline(jd_text: str, candidates: list[Candidate], shortlist_size: int):
    """Run the full extraction + ranking pipeline."""
    settings = get_settings()

    print(f"\n{'='*60}")
    print("  AI Recruiter — Hackathon Submission Pipeline")
    print(f"  Model: {settings.GEMINI_MODEL}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Shortlist size: {shortlist_size}")
    print(f"{'='*60}\n")

    # ── Phase 1: Extract JD ──────────────────────────────────
    print("🔍 Phase 1: Extracting JD signals...")
    t0 = time.time()
    extraction_svc = JDExtractionService()
    jd = await extraction_svc.extract(jd_text)
    t1 = time.time()
    print(f"   ✓ Job: {jd.job_title}")
    print(f"   ✓ Must-have skills: {len(jd.must_have_skills)}")
    print(f"   ✓ Disqualifiers: {len(jd.disqualifiers)}")
    print(f"   ✓ Confidence: {jd.extraction_confidence}")
    print(f"   ⏱  Extraction time: {t1-t0:.2f}s\n")

    # ── Phase 2: Rank candidates ─────────────────────────────
    print("🏆 Phase 2: Ranking candidates...")
    t2 = time.time()
    ranking_svc = CandidateRankingService()
    result = ranking_svc.rank(jd=jd, candidates=candidates, shortlist_size=shortlist_size)
    t3 = time.time()
    print(f"   ✓ Ranked {result.total_candidates_evaluated} candidates")
    print(f"   ✓ Disqualified: {result.disqualified_count}")
    print(f"   ⏱  Ranking time: {t3-t2:.4f}s\n")

    # ── Display results ──────────────────────────────────────
    print(f"{'='*60}")
    print(f"  TOP {shortlist_size} CANDIDATES FOR: {jd.job_title}")
    print(f"{'='*60}")
    for rc in result.shortlist:
        disq = f" ⚠️  DISQ: {rc.disqualifiers_hit[0][:40]}..." if rc.disqualifiers_hit else ""
        print(f"  #{rc.rank:2d}  {rc.name:<20s}  Score: {rc.total_score:6.1f}{disq}")
        print(f"       {rc.recruiter_note}")
        print()

    print(f"  Total pipeline time: {t3-t0:.2f}s")
    print(f"{'='*60}\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="AI Recruiter — Generate hackathon submission ranking output"
    )
    parser.add_argument(
        "--jd",
        type=str,
        default=None,
        help="Path to job description file (.docx or .txt). Uses built-in sample JD if not provided.",
    )
    parser.add_argument(
        "--candidates",
        type=str,
        default="data/sample_candidates.json",
        help="Path to candidates JSON file (default: data/sample_candidates.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/ranked_candidates_output.csv",
        help="Output CSV path (default: output/ranked_candidates_output.csv)",
    )
    parser.add_argument(
        "--shortlist",
        type=int,
        default=10,
        help="Number of candidates in the shortlist (default: 10)",
    )
    args = parser.parse_args()

    # ── Load JD ──────────────────────────────────────────────
    if args.jd:
        print(f"📄 Reading JD from: {args.jd}")
        jd_text = read_jd_file(args.jd)
    else:
        print("📄 No JD file provided — using built-in sample JD")
        jd_text = SAMPLE_JD

    # ── Load candidates ───────────────────────────────────────
    loader = CandidateLoaderService()
    # Override path if specified
    if args.candidates != "data/sample_candidates.json":
        loader.settings.CANDIDATES_FILE = args.candidates
    candidates = loader.load()

    if not candidates:
        print(f"❌ No candidates loaded from '{args.candidates}'")
        print("   Make sure the file exists and contains a 'candidates' array.")
        sys.exit(1)

    # ── Run pipeline ──────────────────────────────────────────
    result = asyncio.run(run_pipeline(jd_text, candidates, args.shortlist))

    # ── Write output ──────────────────────────────────────────
    write_csv(result, args.output)


if __name__ == "__main__":
    main()
