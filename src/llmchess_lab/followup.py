"""Documented follow-up: apply the same engine challenge to Sol and Luna."""
import argparse
import json
from pathlib import Path
import shutil
from dotenv import load_dotenv
from .core import Player,save
from .run import game


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--env-file',required=True);ap.add_argument('--out',default='evidence/episode-02');a=ap.parse_args()
    root=Path(a.out);load_dotenv(a.env_file);p=Player(root,'17')
    protocol=json.loads((root/'followup-protocol.json').read_text())
    for cfg in protocol['games']:game(p,root,cfg,shutil.which('stockfish'))

if __name__=='__main__':main()
