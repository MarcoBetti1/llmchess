"""Published-evidence integrity checks: detect edits that could change the story."""
import json
from pathlib import Path
import shutil
import pytest
from llmchess_lab.analyze import audit

EVIDENCE=Path('evidence/episode-02')

def test_published_evidence_replays_and_accounts_for_every_request(tmp_path):
    root=tmp_path/'episode';shutil.copytree(EVIDENCE,root)
    result=audit(root)
    assert result['requests']==239
    assert result['official_input_count_deltas']=={0:239}
    assert len(result['failures'])==4

def test_audit_rejects_a_missing_followup_game(tmp_path):
    root=tmp_path/'episode';shutil.copytree(EVIDENCE,root)
    (root/'games/luna-black.json').unlink()
    with pytest.raises(AssertionError):audit(root)

def test_audit_rejects_relabeling_an_output_cap_as_checkmate(tmp_path):
    root=tmp_path/'episode';shutil.copytree(EVIDENCE,root)
    path=root/'games/sol-white.json';game=json.loads(path.read_text())
    game.update(rules_completed=True,termination='checkmate')
    path.write_text(json.dumps(game))
    with pytest.raises(AssertionError):audit(root)
