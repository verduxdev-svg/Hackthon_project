import pytest
from pathlib import Path
from app.services.candidate_loader import CandidateLoaderService
from app.models.ranking_models import Candidate

def test_load_json(tmp_path):
    json_file = tmp_path / "candidates.json"
    content = """
    {
      "candidates": [
        {
          "candidate_id": "C101",
          "name": "Jane Doe",
          "profile": {"years_of_experience": 5, "location": "Noida"}
        }
      ]
    }
    """
    json_file.write_text(content, encoding="utf-8")
    loader = CandidateLoaderService()
    loader.settings.CANDIDATES_FILE = str(json_file)
    candidates = loader.load()
    assert len(candidates) == 1
    assert candidates[0].candidate_id == "C101"
    assert candidates[0].name == "Jane Doe"
    assert candidates[0].profile.years_of_experience == 5.0
    assert candidates[0].profile.location == "Noida"

def test_load_jsonl(tmp_path):
    jsonl_file = tmp_path / "candidates.jsonl"
    content = '{"candidate_id": "C201", "name": "Alice Smith", "profile": {"years_of_experience": 3, "location": "Pune"}}\n{"candidate_id": "C202", "name": "Bob Jones", "profile": {"years_of_experience": 8, "location": "Bangalore"}}\n'
    jsonl_file.write_text(content, encoding="utf-8")
    loader = CandidateLoaderService()
    loader.settings.CANDIDATES_FILE = str(jsonl_file)
    candidates = loader.load()
    assert len(candidates) == 2
    assert candidates[0].candidate_id == "C201"
    assert candidates[1].candidate_id == "C202"
    assert candidates[0].profile.years_of_experience == 3.0
    assert candidates[1].profile.years_of_experience == 8.0

def test_load_csv_flat(tmp_path):
    csv_file = tmp_path / "candidates.csv"
    content = "candidate_id,name,summary,profile.years_of_experience,profile.location,willing_to_relocate,skills,notice_period_days\nC301,Charlie Brown,Developer,4,Mumbai,True,Python;AWS,30\n"
    csv_file.write_text(content, encoding="utf-8")
    loader = CandidateLoaderService()
    loader.settings.CANDIDATES_FILE = str(csv_file)
    candidates = loader.load()
    assert len(candidates) == 1
    assert candidates[0].candidate_id == "C301"
    assert candidates[0].name == "Charlie Brown"
    assert candidates[0].profile.years_of_experience == 4.0
    assert candidates[0].profile.location == "Mumbai"
    assert candidates[0].profile.willing_to_relocate is True
    assert len(candidates[0].skills) == 2
    assert candidates[0].skills[0].name == "Python"
    assert candidates[0].skills[1].name == "AWS"
    assert candidates[0].redrob_signals.notice_period_days == 30

def test_load_csv_nested_cells(tmp_path):
    csv_file = tmp_path / "candidates.csv"
    content = 'candidate_id,name,profile,skills\nC401,Delta Force,"{""years_of_experience"": 10, ""location"": ""Noida""}","[{""name"": ""NLP""}]"\n'
    csv_file.write_text(content, encoding="utf-8")
    loader = CandidateLoaderService()
    loader.settings.CANDIDATES_FILE = str(csv_file)
    candidates = loader.load()
    assert len(candidates) == 1
    assert candidates[0].candidate_id == "C401"
    assert candidates[0].name == "Delta Force"
    assert candidates[0].profile.years_of_experience == 10.0
    assert candidates[0].profile.location == "Noida"
    assert len(candidates[0].skills) == 1
    assert candidates[0].skills[0].name == "NLP"
