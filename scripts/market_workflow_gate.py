"""One-shot workflow approval gate. No API request is made by the default plan."""
import argparse
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def gate(config,env,parent):
    if config.get('authorized') is not True:return False
    if env.get('GITHUB_EVENT_NAME')!='push' or env.get('GITHUB_RUN_ATTEMPT')!='1' or env.get('GITHUB_REF')!='refs/heads/main':
        raise ValueError('Paid run requires first attempt of a fresh approval push on main; reruns/dispatch refuse payment')
    if not isinstance(parent,str) or config.get('base_commit')!=parent:
        raise ValueError('Approval is not bound to the direct parent commit; no paid replay')
    if not re.fullmatch(r'[a-f0-9]{40}',parent):raise ValueError('Invalid approval parent')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',config.get('experiment_id','')):raise ValueError('Safe experiment ID required')
    limit=Decimal(config.get('budget_usd','0'))
    if not limit.is_finite() or not 0<limit<=Decimal('2.00'):raise ValueError('Workflow supports at most the proposed $2 experiment budget')
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true');a=p.parse_args()
    c=json.loads((ROOT/'experiments/market-ai/authorization.json').read_text())
    parent=None
    if c.get('authorized') is True:
        parent=subprocess.check_output(['git','rev-parse','HEAD^'],cwd=ROOT,text=True).strip()
    allowed=gate(c,os.environ,parent)
    if not a.execute:
        print('Paid execution authorized for this push:',allowed)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('execute='+str(allowed).lower()+'\n')
        return
    if not allowed:raise ValueError('No paid authorization')
    from cardscan.ai.market_experiment import main as experiment
    sys.argv=['market_experiment','--as-of',str(date.today()),'--settings',str(ROOT/'experiments/market-ai/settings.json'),
              '--experiment-id',c['experiment_id'],'--total-limit-usd',c['budget_usd'],
              '--database',str(ROOT/'local-evidence/market-ai/ledger.sqlite'),
              '--output',str(ROOT/'local-evidence/market-ai/run'),'--execute','--authorize-paid']
    experiment()


if __name__=='__main__':main()
