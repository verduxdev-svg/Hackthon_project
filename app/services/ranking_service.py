"""
Phase 2: Candidate Ranking Engine

This is the core intelligence that ranks candidates the way a great recruiter would.

Design philosophy:
- HYBRID scoring: rule-based + fuzzy skill matching (zero extra LLM calls = low latency)
- TRANSPARENT: every score is broken down so recruiters understand the reasoning
- FAST: ranks 50 candidates in <100ms — pure Python, no I/O
- HONEST: disqualifiers are hard penalties, not soft signals

Scoring Breakdown (max 100 points):
  - Must-have skills match    : 40 pts  (most important — the JD's non-negotiables)
  - Years of experience       : 20 pts  (range fit)
  - Nice-to-have skills       : 15 pts  (differentiation between strong candidates)
  - Behavioral/redrob signals : 10 pts  (platform activity, response rate)
  - Location match            : 10 pts  (preferred location or willing to relocate)
  - Notice period             : 5 pts   (availability speed)
  - Disqualifier hits         : -50 pts per hit (hard penalty — kills rankings)
"""

import logging
from rapidfuzz import fuzz, process

from app.models.jd_models import JDExtractionResult
from app.models.ranking_models import (
    Candidate,
    RankedCandidate,
    RankingResponse,
    ScoreBreakdown,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Scoring Weights
# ─────────────────────────────────────────────────────────────
WEIGHTS = {
    "must_have_skills": 40,
    "experience": 20,
    "nice_to_have_skills": 15,
    "behavioral": 10,
    "location": 10,
    "notice_period": 5,
}

# Fuzzy match threshold — a candidate skill must be ≥70% similar to a JD skill
FUZZY_THRESHOLD = 70

# Hard disqualifier penalty per hit
DISQUALIFIER_PENALTY = 50.0


class CandidateRankingService:
    """
    Ranks candidates against a structured JD extraction result.

    Instantiated once at startup and reused across all requests.
    Stateless — safe for concurrent async requests.
    """

    def rank(
        self,
        jd: JDExtractionResult,
        candidates: list[Candidate],
        shortlist_size: int = 10,
    ) -> RankingResponse:
        """
        Main entry point. Scores all candidates and returns a ranked shortlist.

        Args:
            jd: Validated JDExtractionResult from Phase 1.
            candidates: List of candidate objects.
            shortlist_size: Number of top candidates to include.

        Returns:
            RankingResponse with ranked shortlist and metadata.
        """
        logger.info(
            f"Ranking {len(candidates)} candidates for '{jd.job_title}' "
            f"| shortlist_size={shortlist_size}"
        )

        scored: list[tuple[float, RankedCandidate]] = []

        for candidate in candidates:
            ranked = self._score_candidate(candidate, jd)
            scored.append((ranked.total_score, ranked))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)

        # Assign ranks
        ranked_list = []
        for i, (_, rc) in enumerate(scored):
            rc.rank = i + 1
            ranked_list.append(rc)

        # Count disqualified (candidates with at least 1 disqualifier hit)
        disqualified_count = sum(1 for _, rc in scored if rc.disqualifiers_hit)

        # Return only the shortlist
        shortlist = ranked_list[:shortlist_size]

        logger.info(
            f"Ranking complete | top_candidate='{shortlist[0].name}' "
            f"(score={shortlist[0].total_score:.1f}) | disqualified={disqualified_count}"
        )

        return RankingResponse(
            job_title=jd.job_title,
            total_candidates_evaluated=len(candidates),
            shortlist=shortlist,
            disqualified_count=disqualified_count,
            extraction_confidence=jd.extraction_confidence,
            ranking_metadata={
                "weights": WEIGHTS,
                "fuzzy_threshold": FUZZY_THRESHOLD,
                "disqualifier_penalty_per_hit": DISQUALIFIER_PENALTY,
                "shortlist_size": shortlist_size,
            },
        )

    def _score_candidate(
        self, candidate: Candidate, jd: JDExtractionResult
    ) -> RankedCandidate:
        """Scores a single candidate against the JD extraction."""

        candidate_skill_names = self._get_skill_names(candidate)

        # ── 1. Must-have skills (40 pts) ──────────────────────
        must_matched, must_missing, must_score = self._score_skills(
            jd.must_have_skills, candidate_skill_names, max_points=WEIGHTS["must_have_skills"]
        )

        # ── 2. Experience (20 pts) ────────────────────────────
        exp_score = self._score_experience(candidate, jd)

        # ── 3. Nice-to-have skills (15 pts) ───────────────────
        nice_matched, _, nice_score = self._score_skills(
            jd.nice_to_have_skills, candidate_skill_names, max_points=WEIGHTS["nice_to_have_skills"]
        )

        # ── 4. Behavioral / redrob signals (10 pts) ───────────
        behavioral_score = self._score_behavioral(candidate)

        # ── 5. Location (10 pts) ──────────────────────────────
        location_score = self._score_location(candidate, jd)

        # ── 6. Notice period (5 pts) ──────────────────────────
        notice_score = self._score_notice_period(candidate, jd)

        # ── 7. Disqualifier check ─────────────────────────────
        disqualifiers_hit, disq_penalty = self._check_disqualifiers(candidate, jd)

        # ── Final score ───────────────────────────────────────
        total = (
            must_score
            + exp_score
            + nice_score
            + behavioral_score
            + location_score
            + notice_score
            - disq_penalty
        )
        total = round(total, 2)

        breakdown = ScoreBreakdown(
            must_have_skills_score=round(must_score, 2),
            experience_score=round(exp_score, 2),
            nice_to_have_score=round(nice_score, 2),
            behavioral_score=round(behavioral_score, 2),
            location_score=round(location_score, 2),
            notice_period_score=round(notice_score, 2),
            disqualifier_penalty=round(-disq_penalty, 2),
            total_score=total,
        )

        note = self._generate_recruiter_note(
            candidate, total, must_matched, must_missing, disqualifiers_hit
        )

        return RankedCandidate(
            rank=0,  # assigned after sorting
            candidate_id=candidate.candidate_id,
            name=candidate.name,
            total_score=total,
            score_breakdown=breakdown,
            matched_must_have_skills=must_matched,
            missing_must_have_skills=must_missing,
            matched_nice_to_have=nice_matched,
            disqualifiers_hit=disqualifiers_hit,
            recruiter_note=note,
        )

    # ─────────────────────────────────────────────────────────
    # Scoring Sub-methods
    # ─────────────────────────────────────────────────────────

    def _get_skill_names(self, candidate: Candidate) -> list[str]:
        """Extract all skill name strings from a candidate object."""
        skills = []
        if candidate.skills:
            skills = [s.name for s in candidate.skills if s.name]
        # Also pull from summary if present (catches skills not in the skills array)
        if candidate.summary:
            skills.append(candidate.summary)
        return skills

    def _score_skills(
        self,
        jd_skills: list[str],
        candidate_skill_names: list[str],
        max_points: float,
    ) -> tuple[list[str], list[str], float]:
        """
        Fuzzy skill matching using rapidfuzz.

        For each JD skill, we check if the candidate has a "close enough" match
        in their skill list. This avoids penalizing "PyTorch" vs "pytorch" or
        "vector DB" vs "vector database" differences.

        Returns: (matched_skills, missing_skills, score)
        """
        if not jd_skills:
            return [], [], max_points  # No skills required = full marks

        matched = []
        missing = []

        for jd_skill in jd_skills:
            # rapidfuzz.process.extractOne returns (match, score, index) or None
            result = process.extractOne(
                jd_skill,
                candidate_skill_names,
                scorer=fuzz.partial_ratio,
                score_cutoff=FUZZY_THRESHOLD,
            )
            if result:
                matched.append(jd_skill)
            else:
                missing.append(jd_skill)

        coverage = len(matched) / len(jd_skills)
        score = max_points * coverage
        return matched, missing, score

    def _score_experience(self, candidate: Candidate, jd: JDExtractionResult) -> float:
        """
        Scores experience fit against the JD's min/max range.

        - Full marks: within the required range
        - Partial marks: slightly over/under
        - Penalty: more than 2 years below minimum
        """
        max_pts = float(WEIGHTS["experience"])
        profile = candidate.profile
        if not profile or profile.years_of_experience is None:
            return max_pts * 0.5  # Neutral — unknown experience gets half marks

        yoe = profile.years_of_experience
        min_yoe = jd.minimum_years_experience
        max_yoe = jd.maximum_years_experience

        if yoe < min_yoe:
            gap = min_yoe - yoe
            if gap > 2:
                return max_pts * 0.1  # Significant shortfall
            return max_pts * (1 - gap / (min_yoe + 1))

        if max_yoe and yoe > max_yoe + 3:
            return max_pts * 0.7  # Overqualified (not disqualifying, just suboptimal)

        return max_pts  # Perfect fit

    def _score_behavioral(self, candidate: Candidate) -> float:
        """
        Scores redrob platform signals — proxy for candidate engagement and reliability.

        High interview completion + recruiter response rate = signals strong candidate.
        """
        max_pts = float(WEIGHTS["behavioral"])
        signals = candidate.redrob_signals
        if not signals:
            return max_pts * 0.5  # Neutral

        score = 0.0
        factors = 0

        if signals.recruiter_response_rate is not None:
            score += signals.recruiter_response_rate
            factors += 1

        if signals.interview_completion_rate is not None:
            score += signals.interview_completion_rate
            factors += 1

        if signals.profile_completeness_score is not None:
            score += signals.profile_completeness_score
            factors += 1

        if signals.open_to_work_flag:
            score += 0.5
            factors += 0.5

        # Recency bonus: active in last 30 days = signal of active search
        if signals.last_active_days_ago is not None:
            if signals.last_active_days_ago <= 7:
                score += 1.0
                factors += 1
            elif signals.last_active_days_ago <= 30:
                score += 0.5
                factors += 0.5

        if factors == 0:
            return max_pts * 0.5

        avg = score / factors
        return round(max_pts * min(avg, 1.0), 2)

    def _score_location(self, candidate: Candidate, jd: JDExtractionResult) -> float:
        """
        Scores location fit.

        - Exact match to preferred location: full marks
        - Willing to relocate: 80% marks
        - Remote OK: full marks regardless of location
        - No match + not willing to relocate: 0
        """
        max_pts = float(WEIGHTS["location"])

        if not jd.preferred_locations:
            return max_pts  # No location preference = everyone gets full marks

        if jd.remote_ok:
            return max_pts

        profile = candidate.profile
        if not profile:
            return max_pts * 0.3

        candidate_location = (profile.location or "").lower().strip()

        for preferred in jd.preferred_locations:
            if preferred.lower() in candidate_location or candidate_location in preferred.lower():
                return max_pts  # Location match

        if profile.willing_to_relocate:
            return max_pts * 0.8

        return 0.0  # No match, not willing to relocate

    def _score_notice_period(self, candidate: Candidate, jd: JDExtractionResult) -> float:
        """Scores based on how quickly a candidate can join."""
        max_pts = float(WEIGHTS["notice_period"])

        if jd.preferred_notice_period_days is None:
            return max_pts  # No preference = full marks

        signals = candidate.redrob_signals
        if not signals or signals.notice_period_days is None:
            return max_pts * 0.5  # Unknown = neutral

        notice = signals.notice_period_days
        preferred = jd.preferred_notice_period_days

        if notice <= preferred:
            return max_pts
        elif notice <= preferred * 2:
            return max_pts * 0.5
        else:
            return 0.0  # Way outside window

    def _check_disqualifiers(
        self, candidate: Candidate, jd: JDExtractionResult
    ) -> tuple[list[str], float]:
        """
        Checks if any JD disqualifiers apply to this candidate.

        Disqualifiers are hard penalties. A single hit = -50 points.
        Uses a smart matching strategy:
        - For consulting disqualifiers: checks career_history company_type directly
        - For skill-based disqualifiers: checks if candidate ONLY has those skills
        - For multi-word disqualifiers: requires >=2 keywords to co-occur

        Returns: (list of disqualifiers hit, total penalty)
        """
        if not jd.disqualifiers:
            return [], 0.0

        hit_disqualifiers = []
        candidate_text = self._build_candidate_text(candidate).lower()

        for disqualifier in jd.disqualifiers:
            if self._disqualifier_applies(disqualifier, candidate, candidate_text):
                hit_disqualifiers.append(disqualifier)

        penalty = len(hit_disqualifiers) * DISQUALIFIER_PENALTY
        return hit_disqualifiers, penalty

    def _disqualifier_applies(self, disqualifier: str, candidate: Candidate, candidate_text: str) -> bool:
        """
        Determines if a disqualifier applies to a candidate using context-aware matching.

        Strategy:
        1. Consulting disqualifiers: check if ALL career history is at consulting companies
        2. Research/academia disqualifiers: check career history company_type
        3. Skill-only disqualifiers: check if candidate ENTIRELY lacks certain skills
        4. Generic: require >=2 specific keywords to co-occur in candidate text
        """
        disq_lower = disqualifier.lower()

        # ── Consulting-specific check ──────────────────────────
        # Only fire if the candidate's ENTIRE history is consulting, not just one entry
        consulting_keywords = {"tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
                               "hcl", "tech mahindra", "ibm", "consulting", "consultancy"}
        if any(w in disq_lower for w in ["consulting", "consultancy", "tcs", "infosys", "wipro"]):
            if candidate.career_history:
                all_consulting = all(
                    entry.company_type in ("consulting",) or
                    any(co in (entry.company or "").lower() for co in
                        ["tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini",
                         "hcl", "tech mahindra"])
                    for entry in candidate.career_history
                )
                return all_consulting
            return False

        # ── Research/academia-specific check ──────────────────
        if "research" in disq_lower and ("production" in disq_lower or "deployment" in disq_lower):
            # Only fire if candidate is ONLY in research roles
            if candidate.career_history:
                all_research = all(
                    entry.company_type in ("research", "academia")
                    for entry in candidate.career_history
                )
                return all_research
            return False

        # ── Computer vision / speech without NLP ──────────────
        if "computer vision" in disq_lower or "vision" in disq_lower:
            has_cv = "computer vision" in candidate_text
            has_nlp = any(kw in candidate_text for kw in ["nlp", "natural language", "text", "embedding", "transformer"])
            return has_cv and not has_nlp

        # ── Generic: require >=2 meaningful keywords to co-occur ──
        keywords = self._extract_disqualifier_keywords(disqualifier)
        if not keywords:
            return False
        # Need at least 2 keywords to match, or 1 if very specific (len > 6 chars)
        specific_keywords = [k for k in keywords if len(k) > 5]
        if specific_keywords:
            matches = sum(1 for k in specific_keywords if k in candidate_text)
            return matches >= min(2, len(specific_keywords))
        else:
            matches = sum(1 for k in keywords if k in candidate_text)
            return matches >= 2

    def _build_candidate_text(self, candidate: Candidate) -> str:
        """Builds a flat text blob from candidate data for disqualifier matching."""
        parts = [candidate.name]
        if candidate.summary:
            parts.append(candidate.summary)
        if candidate.profile:
            if candidate.profile.current_industry:
                parts.append(candidate.profile.current_industry)
        if candidate.career_history:
            for entry in candidate.career_history:
                if entry.company:
                    parts.append(entry.company)
                if entry.company_type:
                    parts.append(entry.company_type)
                if entry.title:
                    parts.append(entry.title)
        if candidate.skills:
            parts.extend([s.name for s in candidate.skills if s.name])
        return " ".join(parts)

    def _extract_disqualifier_keywords(self, disqualifier: str) -> list[str]:
        """
        Extracts the most specific keywords from a disqualifier phrase.

        E.g., "only consulting firm experience (TCS, Infosys, Wipro)"
              → ["tcs", "infosys", "wipro", "consulting"]
        """
        # Remove common filler words
        stopwords = {
            "only", "pure", "without", "with", "no", "not", "from",
            "a", "an", "the", "or", "and", "of", "in", "for", "to"
        }
        words = disqualifier.lower().replace("(", " ").replace(")", " ").replace(",", " ").split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        return keywords[:5]  # Use top-5 most specific keywords

    def _generate_recruiter_note(
        self,
        candidate: Candidate,
        total_score: float,
        must_matched: list[str],
        must_missing: list[str],
        disqualifiers_hit: list[str],
    ) -> str:
        """Generates a 1-2 sentence human-readable note for the recruiter."""
        name = candidate.name

        if disqualifiers_hit:
            return (
                f"{name} hits a hard disqualifier: {disqualifiers_hit[0]}. "
                f"Not recommended for this role despite other strengths."
            )

        if total_score >= 80:
            skills_str = ", ".join(must_matched[:3]) if must_matched else "core skills"
            return (
                f"Strong match. {name} demonstrates {skills_str} and fits the experience range. "
                f"Recommend for immediate interview."
            )
        elif total_score >= 55:
            missing_str = (f"Missing: {', '.join(must_missing[:2])}." if must_missing else "")
            return (
                f"Good candidate with solid profile. {missing_str} "
                f"Consider for second-round screening."
            )
        elif total_score >= 30:
            missing_str = f"Gaps in: {', '.join(must_missing[:3])}." if must_missing else ""
            return (
                f"Partial match. {missing_str} May need upskilling for this role."
            )
        else:
            return (
                f"Below threshold. {name} lacks several must-have requirements "
                f"for this position."
            )
