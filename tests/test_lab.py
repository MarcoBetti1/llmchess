import io
import json
from decimal import Decimal
import chess
import chess.pgn
import httpx
import pytest
from llmchess_lab.core import Ledger, Player, BudgetStop, UncertainRequest, parse_reply, bound_cost, prompt
from llmchess_lab.run import make_cases
from llmchess_simple.referee import Referee
from llmchess_simple.llm_play import annotated_history_from_board, pgn_tail_from_board


def test_generated_cases_have_exact_exhaustive_mate_keys():
    cases=make_cases()
    assert len(cases)==12 and len({c['fen'] for c in cases})==12
    for c in cases:
        b=chess.Board(c['fen']);assert b.is_valid()
        actual=[]
        for m in b.legal_moves:
            t=b.copy();t.push(m)
            if t.is_checkmate():actual.append(m.uci())
        assert sorted(actual)==c['mate_moves']
        assert c['mate_moves'] and all(m in prompt(b) for m in c['mate_moves'])

@pytest.mark.parametrize('text,failure',[
    ('e2e4','invalid_json'),
    ('{"move":"e2e5","comment":"advance"}','illegal_move'),
    ('{"move":"e2e4","comment":"ok","other":1}','invalid_schema'),
    ('{"move":"0000","comment":"pass"}','invalid_uci'),
    ('{"move":"e2e4 g1f3","comment":"two"}','invalid_uci')])
def test_no_silent_move_repairs(text,failure):
    b=chess.Board();p=parse_reply(text,b)
    assert not p['legal'] and p['failure']==failure and not b.move_stack


def test_promotion_and_legality():
    b=chess.Board('8/P7/8/8/8/5k2/8/5K2 w - - 0 1')
    assert parse_reply('{"move":"a7a8n","comment":"underpromotion"}',b)['legal']
    assert not parse_reply('{"move":"a7a8","comment":"missing promotion"}',b)['legal']


def test_durable_budget_and_uncertain_reservations(tmp_path):
    x=Ledger(tmp_path,'1');x.reserve('a',Decimal('.8'),{})
    with pytest.raises(UncertainRequest):x.reserve('a',Decimal('.1'),{})
    with pytest.raises(BudgetStop):Ledger(tmp_path,'1').reserve('b',Decimal('.3'),{})
    x.settle('a',Decimal('.2'),{});x.reserve('b',Decimal('.8'),{})
    assert x.total()==1
    with pytest.raises(ValueError):Ledger(tmp_path,'2').total()


def test_usage_includes_reasoning_without_double_counting():
    assert bound_cost('gpt-6-astra',1000,1000)==Decimal('.0625')


def test_official_count_and_request_receipt(tmp_path):
    sent=[]
    def handler(req):
        body=json.loads(req.content);sent.append((req.url.path,body))
        if req.url.path.endswith('input_tokens'):return httpx.Response(200,json={'input_tokens':400})
        return httpx.Response(200,json={'status':'completed','model':'gpt-6-astra',
            'usage':{'input_tokens':400,'output_tokens':800,'output_tokens_details':{'reasoning_tokens':780}},
            'output':[{'type':'message','content':[{'type':'output_text','text':'{"move":"e2e4","comment":"Take the center."}'}]}]})
    p=Player(tmp_path,client=httpx.Client(base_url='https://example.test/',transport=httpx.MockTransport(handler)))
    r=p.play('gpt-6-astra',chess.Board(),'test')
    assert r['parsed']['legal'] and r['input_count_delta']==0
    assert p.ledger.total()==Decimal('.045')
    assert p.play('gpt-6-astra',chess.Board(),'test')==r and len(sent)==2
    assert sent[0][1]['model']==sent[1][1]['model']


def test_incomplete_output_is_not_a_valid_chess_move(tmp_path):
    def handler(req):
        if req.url.path.endswith('input_tokens'):return httpx.Response(200,json={'input_tokens':100})
        return httpx.Response(200,json={'status':'incomplete','model':'gpt-6-astra','usage':{'input_tokens':100,'output_tokens':2048},
            'output':[{'type':'message','content':[{'type':'output_text','text':'{"move":"e2e4","comment":"center"}'}]}]})
    p=Player(tmp_path,client=httpx.Client(base_url='https://example.test/',transport=httpx.MockTransport(handler)))
    assert not p.play('gpt-6-astra',chess.Board(),'test')['parsed']['legal']


def test_custom_position_roundtrips_pgn_and_history():
    ref=Referee('8/8/8/8/8/1k6/8/K6R w - - 0 40')
    ref.apply_uci('h1h3')
    restored=chess.pgn.read_game(io.StringIO(ref.pgn()))
    assert restored.end().board().fen()==ref.board.fen()
    assert 'Rh3+' in annotated_history_from_board(ref.board)
    assert '40. Rh3+' in pgn_tail_from_board(ref.board,20)


def test_engine_cannot_apply_illegal_move():
    r=Referee()
    with pytest.raises(ValueError):r.engine_apply(chess.Move.from_uci('e2e5'))
