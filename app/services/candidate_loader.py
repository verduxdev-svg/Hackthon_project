import json
import logging
import csv
from pathlib import Path
from app.core.config import get_settings
from app.models.ranking_models import Candidate
logger = logging.getLogger(__name__)

class LazyCandidateList:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._count = None

    def _determine_count(self) -> int:
        try:
            suffix = self.filepath.suffix.lower()
            if suffix == '.jsonl':
                count = 0
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            count += 1
                return count
            elif suffix == '.csv':
                count = 0
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            count += 1
                return max(0, count - 1)
            elif suffix == '.json':
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data = data.get('candidates', data.get('data', []))
                    return len(data)
        except Exception:
            return 0
        return 0

    def __len__(self) -> int:
        if self._count is None:
            self._count = self._determine_count()
        return self._count

    def __getitem__(self, index):
        if index < 0:
            index = len(self) + index
        if index < 0 or index >= len(self):
            raise IndexError("list index out of range")
        for idx, item in enumerate(self):
            if idx == index:
                return item
        raise IndexError("list index out of range")

    def __iter__(self):
        suffix = self.filepath.suffix.lower()
        if suffix == '.json':
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data = data.get('candidates', data.get('data', []))
                for c in data:
                    yield Candidate(**c)
        elif suffix == '.jsonl':
            with open(self.filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        yield Candidate(**json.loads(line))
        elif suffix == '.csv':
            with open(self.filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    yield Candidate(**self._parse_csv_row(row))

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

class CandidateLoaderService:
    def __init__(self):
        self.settings = get_settings()
        self._candidates = None
        self._loaded = False

    def load(self):
        if self._loaded:
            return self._candidates
        candidates_path = Path(self.settings.CANDIDATES_FILE)
        if not candidates_path.exists():
            logger.warning(f"Candidates file not found at '{candidates_path}'.")
            self._candidates = []
            self._loaded = True
            return self._candidates
        self._candidates = LazyCandidateList(candidates_path)
        self._loaded = True
        logger.info(f"Initialized lazy candidates list from '{candidates_path}'")
        return self._candidates

    def get_candidates(self):
        if not self._loaded:
            return self.load()
        return self._candidates

    def count(self) -> int:
        return len(self.get_candidates())