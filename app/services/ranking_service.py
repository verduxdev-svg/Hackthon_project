import logging
from rapidfuzz import fuzz, process
import numpy as np
from sentence_transformers import SentenceTransformer, util
from app.models.jd_models import JDExtractionResult
from app.models.ranking_models import Candidate, RankedCandidate, RankingResponse, ScoreBreakdown
logger = logging.getLogger(__name__)
WEIGHTS = {'must_have_skills': 40, 'experience': 20, 'nice_to_have_skills': 15, 'behavioral': 10, 'location': 10, 'notice_period': 5}
FUZZY_THRESHOLD = 70
DISQUALIFIER_PENALTY = 50.0

class CandidateRankingService:

    def __init__(self):
        self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self._embeddings_cache = {}
        logger.info('CandidateRankingService initialized with SentenceTransformer')

    def rank(self, jd: JDExtractionResult, candidates: list[Candidate], shortlist_size: int=10) -> RankingResponse:
        logger.info(f"Ranking {len(candidates)} candidates for '{jd.job_title}' | shortlist_size={shortlist_size}")
        must_jd_embs = self._encode_texts(jd.must_have_skills)
        nice_jd_embs = self._encode_texts(jd.nice_to_have_skills)
        running_top = []
        disqualified_count = 0
        total_evaluated = 0
        chunk = []
        chunk_size = 5000
        for cand in candidates:
            chunk.append(cand)
            if len(chunk) >= chunk_size:
                disqualified_count += self._process_chunk(chunk, jd, must_jd_embs, nice_jd_embs, running_top, shortlist_size)
                total_evaluated += len(chunk)
                chunk = []
        if chunk:
            disqualified_count += self._process_chunk(chunk, jd, must_jd_embs, nice_jd_embs, running_top, shortlist_size)
            total_evaluated += len(chunk)
        running_top.sort(key=lambda x: x[0], reverse=True)
        ranked_list = []
        for rank_idx, (score, candidate, raw_data) in enumerate(running_top[:shortlist_size]):
            breakdown = ScoreBreakdown(
                must_have_skills_score=round(raw_data['must_score'], 2),
                experience_score=round(raw_data['exp_score'], 2),
                nice_to_have_score=round(raw_data['nice_score'], 2),
                behavioral_score=round(raw_data['behavioral_score'], 2),
                location_score=round(raw_data['location_score'], 2),
                notice_period_score=round(raw_data['notice_score'], 2),
                disqualifier_penalty=round(-raw_data['disq_penalty'], 2),
                total_score=round(score, 2)
            )
            note = self._generate_recruiter_note(
                candidate, score, raw_data['must_matched'], raw_data['must_missing'], raw_data['disqualifiers_hit']
            )
            rc = RankedCandidate(
                rank=rank_idx + 1,
                candidate_id=candidate.candidate_id,
                name=candidate.name,
                total_score=round(score, 2),
                score_breakdown=breakdown,
                matched_must_have_skills=raw_data['must_matched'],
                missing_must_have_skills=raw_data['must_missing'],
                matched_nice_to_have=raw_data['nice_matched'],
                disqualifiers_hit=raw_data['disqualifiers_hit'],
                recruiter_note=note
            )
            ranked_list.append(rc)
        logger.info(f"Ranking complete | top_candidate='{ranked_list[0].name if ranked_list else None}' (score={ranked_list[0].total_score if ranked_list else 0.0}) | disqualified={disqualified_count}")
        return RankingResponse(
            job_title=jd.job_title,
            total_candidates_evaluated=total_evaluated,
            shortlist=ranked_list,
            disqualified_count=disqualified_count,
            extraction_confidence=jd.extraction_confidence,
            ranking_metadata={'weights': WEIGHTS, 'fuzzy_threshold': FUZZY_THRESHOLD, 'disqualifier_penalty_per_hit': DISQUALIFIER_PENALTY, 'shortlist_size': shortlist_size}
        )

    def _process_chunk(self, chunk: list[Candidate], jd: JDExtractionResult, must_jd_embs: np.ndarray, nice_jd_embs: np.ndarray, running_top: list, shortlist_size: int) -> int:
        self._pre_encode_candidates(chunk)
        chunk_disq = 0
        chunk_scored = []
        for candidate in chunk:
            raw_data = self._fast_score_candidate(candidate, jd, must_jd_embs, nice_jd_embs)
            if raw_data['total'] <= 0.0:
                continue
            if raw_data['disqualifiers_hit']:
                chunk_disq += 1
            chunk_scored.append((raw_data['total'], candidate, raw_data))
        running_top.extend(chunk_scored)
        running_top.sort(key=lambda x: x[0], reverse=True)
        del running_top[max(shortlist_size * 2, 500):]
        return chunk_disq

    def _pre_encode_candidates(self, candidates: list[Candidate]):
        texts_to_encode = set()
        candidates_to_process = []
        for cand in candidates:
            if cand.skill_embeddings is None and cand.candidate_id in self._embeddings_cache:
                cand.skill_embeddings = self._embeddings_cache[cand.candidate_id]
            if cand.skill_embeddings is None:
                skill_names = []
                if cand.skills:
                    skill_names.extend([s.name for s in cand.skills if s.name])
                if cand.summary:
                    skill_names.append(cand.summary)
                if skill_names:
                    texts_to_encode.update(skill_names)
                    candidates_to_process.append((cand, skill_names))
        if not texts_to_encode:
            return
        texts_list = list(texts_to_encode)
        embeddings_dict = {}
        batch_size = 2048
        for i in range(0, len(texts_list), batch_size):
            chunk = texts_list[i : i + batch_size]
            encoded = self._embedder.encode(
                chunk,
                batch_size=256,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            for text, emb in zip(chunk, encoded):
                embeddings_dict[text] = emb.astype(np.float32)
        for cand, skill_names in candidates_to_process:
            cand_embs = []
            for name in skill_names:
                if name in embeddings_dict:
                    cand_embs.append(embeddings_dict[name])
            if cand_embs:
                stacked = np.stack(cand_embs)
                cand.skill_embeddings = stacked.flatten().tolist()
                self._embeddings_cache[cand.candidate_id] = cand.skill_embeddings
            else:
                cand.skill_embeddings = []
                self._embeddings_cache[cand.candidate_id] = []

    def _fast_score_candidate(self, candidate: Candidate, jd: JDExtractionResult, must_jd_embs: np.ndarray, nice_jd_embs: np.ndarray) -> dict:
        must_matched, must_missing, must_score = self._score_skills_precomputed(jd.must_have_skills, must_jd_embs, candidate, max_points=WEIGHTS['must_have_skills'])
        exp_score = self._score_experience(candidate, jd)
        nice_matched, _, nice_score = self._score_skills_precomputed(jd.nice_to_have_skills, nice_jd_embs, candidate, max_points=WEIGHTS['nice_to_have_skills'])
        behavioral_score = self._score_behavioral(candidate)
        location_score = self._score_location(candidate, jd)
        notice_score = self._score_notice_period(candidate, jd)
        disqualifiers_hit, disq_penalty = self._check_disqualifiers(candidate, jd)
        total = must_score + exp_score + nice_score + behavioral_score + location_score + notice_score - disq_penalty
        return {
            'total': round(total, 2),
            'must_score': must_score,
            'exp_score': exp_score,
            'nice_score': nice_score,
            'behavioral_score': behavioral_score,
            'location_score': location_score,
            'notice_score': notice_score,
            'disq_penalty': disq_penalty,
            'must_matched': must_matched,
            'must_missing': must_missing,
            'nice_matched': nice_matched,
            'disqualifiers_hit': disqualifiers_hit
        }

    def _score_candidate(self, candidate: Candidate, jd: JDExtractionResult) -> RankedCandidate:
        must_matched, must_missing, must_score = self._score_skills(jd.must_have_skills, candidate, max_points=WEIGHTS['must_have_skills'])
        exp_score = self._score_experience(candidate, jd)
        nice_matched, _, nice_score = self._score_skills(jd.nice_to_have_skills, candidate, max_points=WEIGHTS['nice_to_have_skills'])
        behavioral_score = self._score_behavioral(candidate)
        location_score = self._score_location(candidate, jd)
        notice_score = self._score_notice_period(candidate, jd)
        disqualifiers_hit, disq_penalty = self._check_disqualifiers(candidate, jd)
        total = must_score + exp_score + nice_score + behavioral_score + location_score + notice_score - disq_penalty
        total = round(total, 2)
        breakdown = ScoreBreakdown(must_have_skills_score=round(must_score, 2), experience_score=round(exp_score, 2), nice_to_have_score=round(nice_score, 2), behavioral_score=round(behavioral_score, 2), location_score=round(location_score, 2), notice_period_score=round(notice_score, 2), disqualifier_penalty=round(-disq_penalty, 2), total_score=total)
        note = self._generate_recruiter_note(candidate, total, must_matched, must_missing, disqualifiers_hit)
        return RankedCandidate(rank=0, candidate_id=candidate.candidate_id, name=candidate.name, total_score=total, score_breakdown=breakdown, matched_must_have_skills=must_matched, missing_must_have_skills=must_missing, matched_nice_to_have=nice_matched, disqualifiers_hit=disqualifiers_hit, recruiter_note=note)

    def _get_skill_names(self, candidate: Candidate) -> list[str]:
        skills = []
        if candidate.skills:
            skills = [s.name for s in candidate.skills if s.name]
        if candidate.summary:
            skills.append(candidate.summary)
        return skills

    def _encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._embedder.get_embedding_dimension()), dtype=np.float32)
        return np.array(self._embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True), dtype=np.float32)

    def _ensure_candidate_embeddings(self, candidate: Candidate) -> np.ndarray:
        if candidate.skill_embeddings is not None:
            return np.array(candidate.skill_embeddings, dtype=np.float32).reshape(-1, self._embedder.get_embedding_dimension())
        skill_names = []
        if candidate.skills:
            skill_names.extend([s.name for s in candidate.skills if s.name])
        if candidate.summary:
            skill_names.append(candidate.summary)
        if not skill_names:
            return np.zeros((0, self._embedder.get_embedding_dimension()))
        embeddings = self._encode_texts(skill_names)
        candidate.skill_embeddings = embeddings.flatten().tolist()
        return embeddings

    def _score_skills(self, jd_skills: list[str], candidate: Candidate, max_points: float) -> tuple[list[str], list[str], float]:
        jd_embeddings = self._encode_texts(jd_skills)
        cand_embeddings = self._ensure_candidate_embeddings(candidate)
        if jd_embeddings.shape[0] == 0:
            return ([], [], max_points)
        if cand_embeddings.shape[0] == 0:
            return ([], jd_skills, 0.0)
        sim_matrix = util.cos_sim(jd_embeddings, cand_embeddings).numpy()
        matched: list[str] = []
        missing: list[str] = []
        for idx, jd_skill in enumerate(jd_skills):
            best_sim = float(sim_matrix[idx].max()) if sim_matrix.shape[1] > 0 else 0.0
            if best_sim >= 0.7:
                matched.append(jd_skill)
            else:
                missing.append(jd_skill)
        coverage = len(matched) / len(jd_skills) if jd_skills else 1.0
        score = max_points * coverage
        return (matched, missing, score)

    def _score_skills_precomputed(self, jd_skills: list[str], jd_embeddings: np.ndarray, candidate: Candidate, max_points: float) -> tuple[list[str], list[str], float]:
        if jd_embeddings.shape[0] == 0:
            return ([], [], max_points)
        cand_embeddings = self._ensure_candidate_embeddings(candidate)
        if cand_embeddings.shape[0] == 0:
            return ([], jd_skills, 0.0)
        sim_matrix = util.cos_sim(jd_embeddings, cand_embeddings).numpy()
        matched: list[str] = []
        missing: list[str] = []
        for idx, jd_skill in enumerate(jd_skills):
            best_sim = float(sim_matrix[idx].max()) if sim_matrix.shape[1] > 0 else 0.0
            if best_sim >= 0.7:
                matched.append(jd_skill)
            else:
                missing.append(jd_skill)
        coverage = len(matched) / len(jd_skills) if jd_skills else 1.0
        score = max_points * coverage
        return (matched, missing, score)

    def _score_experience(self, candidate: Candidate, jd: JDExtractionResult) -> float:
        max_pts = float(WEIGHTS['experience'])
        profile = candidate.profile
        if not profile or profile.years_of_experience is None:
            return max_pts * 0.5
        yoe = profile.years_of_experience
        min_yoe = jd.minimum_years_experience
        max_yoe = jd.maximum_years_experience
        if yoe < min_yoe:
            gap = min_yoe - yoe
            if gap > 2:
                return max_pts * 0.1
            return max_pts * (1 - gap / (min_yoe + 1))
        if max_yoe and yoe > max_yoe + 3:
            return max_pts * 0.7
        return max_pts

    def _score_behavioral(self, candidate: Candidate) -> float:
        max_pts = float(WEIGHTS['behavioral'])
        signals = candidate.redrob_signals
        if not signals:
            return max_pts * 0.5
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
        max_pts = float(WEIGHTS['location'])
        if not jd.preferred_locations:
            return max_pts
        if jd.remote_ok:
            return max_pts
        profile = candidate.profile
        if not profile:
            return max_pts * 0.3
        candidate_location = (profile.location or '').lower().strip()
        for preferred in jd.preferred_locations:
            if preferred.lower() in candidate_location or candidate_location in preferred.lower():
                return max_pts
        if profile.willing_to_relocate:
            return max_pts * 0.8
        return 0.0

    def _score_notice_period(self, candidate: Candidate, jd: JDExtractionResult) -> float:
        max_pts = float(WEIGHTS['notice_period'])
        if jd.preferred_notice_period_days is None:
            return max_pts
        signals = candidate.redrob_signals
        if not signals or signals.notice_period_days is None:
            return max_pts * 0.5
        notice = signals.notice_period_days
        preferred = jd.preferred_notice_period_days
        if notice <= preferred:
            return max_pts
        elif notice <= preferred * 2:
            return max_pts * 0.5
        else:
            return 0.0

    def _check_disqualifiers(self, candidate: Candidate, jd: JDExtractionResult) -> tuple[list[str], float]:
        if not jd.disqualifiers:
            return ([], 0.0)
        hit_disqualifiers = []
        candidate_text = self._build_candidate_text(candidate).lower()
        for disqualifier in jd.disqualifiers:
            if self._disqualifier_applies(disqualifier, candidate, candidate_text):
                hit_disqualifiers.append(disqualifier)
        penalty = len(hit_disqualifiers) * DISQUALIFIER_PENALTY
        return (hit_disqualifiers, penalty)

    def _disqualifier_applies(self, disqualifier: str, candidate: Candidate, candidate_text: str) -> bool:
        disq_lower = disqualifier.lower()
        consulting_keywords = {'tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'capgemini', 'hcl', 'tech mahindra', 'ibm', 'consulting', 'consultancy'}
        if any((w in disq_lower for w in ['consulting', 'consultancy', 'tcs', 'infosys', 'wipro'])):
            if candidate.career_history:
                all_consulting = all((entry.company_type in ('consulting',) or any((co in (entry.company or '').lower() for co in ['tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'capgemini', 'hcl', 'tech mahindra'])) for entry in candidate.career_history))
                return all_consulting
            return False
        if 'research' in disq_lower and ('production' in disq_lower or 'deployment' in disq_lower):
            if candidate.career_history:
                all_research = all((entry.company_type in ('research', 'academia') for entry in candidate.career_history))
                return all_research
            return False
        if 'computer vision' in disq_lower or 'vision' in disq_lower:
            has_cv = 'computer vision' in candidate_text
            has_nlp = any((kw in candidate_text for kw in ['nlp', 'natural language', 'text', 'embedding', 'transformer']))
            return has_cv and (not has_nlp)
        keywords = self._extract_disqualifier_keywords(disqualifier)
        if not keywords:
            return False
        specific_keywords = [k for k in keywords if len(k) > 5]
        if specific_keywords:
            matches = sum((1 for k in specific_keywords if k in candidate_text))
            return matches >= min(2, len(specific_keywords))
        else:
            matches = sum((1 for k in keywords if k in candidate_text))
            return matches >= 2

    def _build_candidate_text(self, candidate: Candidate) -> str:
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
        return ' '.join(parts)

    def _extract_disqualifier_keywords(self, disqualifier: str) -> list[str]:
        stopwords = {'only', 'pure', 'without', 'with', 'no', 'not', 'from', 'a', 'an', 'the', 'or', 'and', 'of', 'in', 'for', 'to'}
        words = disqualifier.lower().replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
        keywords = [w for w in words if w not in stopwords and len(w) > 2]
        return keywords[:5]

    def _generate_recruiter_note(self, candidate: Candidate, total_score: float, must_matched: list[str], must_missing: list[str], disqualifiers_hit: list[str]) -> str:
        name = candidate.name
        if disqualifiers_hit:
            return f'{name} hits a hard disqualifier: {disqualifiers_hit[0]}. Not recommended for this role despite other strengths.'
        if total_score >= 80:
            skills_str = ', '.join(must_matched[:3]) if must_matched else 'core skills'
            return f'Strong match. {name} demonstrates {skills_str} and fits the experience range. Recommend for immediate interview.'
        elif total_score >= 55:
            missing_str = f"Missing: {', '.join(must_missing[:2])}." if must_missing else ''
            return f'Good candidate with solid profile. {missing_str} Consider for second-round screening.'
        elif total_score >= 30:
            missing_str = f"Gaps in: {', '.join(must_missing[:3])}." if must_missing else ''
            return f'Partial match. {missing_str} May need upskilling for this role.'
        else:
            return f'Below threshold. {name} lacks several must-have requirements for this position.'