import json
import logging
from pathlib import Path
from app.core.config import get_settings
from app.models.ranking_models import Candidate
logger = logging.getLogger(__name__)

class CandidateLoaderService:

    def __init__(self):
        self.settings = get_settings()
        self._candidates: list[Candidate] = []
        self._loaded = False

    def load(self) -> list[Candidate]:
        if self._loaded:
            return self._candidates
        candidates_path = Path(self.settings.CANDIDATES_FILE)
        if not candidates_path.exists():
            logger.warning(f"Candidates file not found at '{candidates_path}'. POST /api/rank-candidates will still work with inline candidate data.")
            self._loaded = True
            return []
        try:
            suffix = candidates_path.suffix.lower()
            raw = candidates_path.read_text(encoding='utf-8')
            data = []
            if suffix == '.json':
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed.get('candidates', parsed.get('data', []))
                elif isinstance(parsed, list):
                    data = parsed
            elif suffix == '.jsonl':
                for line in raw.splitlines():
                    if line.strip():
                        data.append(json.loads(line))
            elif suffix == '.csv':
                import csv
                import io
                reader = csv.DictReader(io.StringIO(raw))
                for row in reader:
                    data.append(self._parse_csv_row(row))
            else:
                logger.error(f"Unsupported candidate file extension '{suffix}'. Supported: .json, .jsonl, .csv")
                self._loaded = True
                return []
            self._candidates = [Candidate(**c) for c in data]
            self._loaded = True
            logger.info(f"Loaded {len(self._candidates)} candidates from '{candidates_path}'")
            return self._candidates
        except Exception as e:
            logger.error(f"Failed to load candidates from '{candidates_path}': {e}")
            self._loaded = True
            return []

    def _parse_csv_row(self, row: dict) -> dict:
        candidate = {}
        profile = {}
        redrob_signals = {}
        skills = []
        career_history = []
        for col, val in row.items():
            if not col or val is None or val.strip() == "":
                continue
            val = val.strip()
            col = col.strip()
            parsed_val = None
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                try:
                    parsed_val = json.loads(val)
                except Exception:
                    pass
            if parsed_val is not None:
                if col == 'profile':
                    profile.update(parsed_val)
                elif col == 'redrob_signals':
                    redrob_signals.update(parsed_val)
                elif col == 'skills':
                    if isinstance(parsed_val, list):
                        skills.extend(parsed_val)
                elif col == 'career_history':
                    if isinstance(parsed_val, list):
                        career_history.extend(parsed_val)
                else:
                    candidate[col] = parsed_val
                continue
            if '.' in col:
                parts = col.split('.')
                parent = parts[0]
                child = parts[1]
                if parent == 'profile':
                    profile[child] = self._parse_val(val)
                elif parent == 'redrob_signals':
                    redrob_signals[child] = self._parse_val(val)
                continue
            if col in ['candidate_id', 'name', 'summary']:
                candidate[col] = val
            elif col == 'skills':
                delim = ';' if ';' in val else ','
                items = [s.strip() for s in val.split(delim) if s.strip()]
                for s in items:
                    skills.append({"name": s, "proficiency": "intermediate", "years": 0.0})
            elif col == 'profile_location':
                profile['location'] = val
            elif col == 'years_of_experience':
                try:
                    profile['years_of_experience'] = float(val)
                except ValueError:
                    pass
            elif col == 'willing_to_relocate':
                profile['willing_to_relocate'] = val.lower() in ['true', '1', 'yes', 'y']
            elif col == 'current_industry':
                profile['current_industry'] = val
            elif col == 'education_tier':
                profile['education_tier'] = val
            elif col == 'notice_period_days':
                try:
                    redrob_signals['notice_period_days'] = int(float(val))
                except ValueError:
                    pass
            elif col == 'open_to_work':
                redrob_signals['open_to_work_flag'] = val.lower() in ['true', '1', 'yes', 'y']
            else:
                candidate[col] = self._parse_val(val)
        if profile:
            candidate['profile'] = profile
        if redrob_signals:
            candidate['redrob_signals'] = redrob_signals
        if skills:
            candidate['skills'] = skills
        if career_history:
            candidate['career_history'] = career_history
        return candidate

    def _parse_val(self, val: str):
        val_lower = val.lower()
        if val_lower in ['true', 'yes', 'y']:
            return True
        if val_lower in ['false', 'no', 'n']:
            return False
        try:
            if '.' in val:
                return float(val)
            return int(val)
        except ValueError:
            return val

    def get_candidates(self) -> list[Candidate]:
        if not self._loaded:
            return self.load()
        return self._candidates

    def count(self) -> int:
        return len(self.get_candidates())