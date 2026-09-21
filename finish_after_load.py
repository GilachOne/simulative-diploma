"""One-off local continuation: export and execute reports when 2023 is complete.

Run alongside the loader. Stops after two hours if daily coverage is incomplete.
It does not publish, upload, or claim that remote deployment is complete.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'data/local-config.json').read_text('utf-8'))
for key,value in cfg['loader_env'].items():os.environ[key]=str(value)
from etl import connect

def main():
    deadline=time.monotonic()+7200
    previous=None
    while time.monotonic()<deadline:
        conn=connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM etl_days WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31'")
                count=cur.fetchone()[0]
        finally:conn.close()
        if count!=previous:
            print('2023 coverage:',count,'/ 365',flush=True)
            previous=count
        if count==365:break
        time.sleep(30)
    else:
        raise RuntimeError('2023 coverage remains incomplete; rerun the missing range before research')
    subprocess.run([sys.executable,str(ROOT/'export_research.py')],check=True,cwd=ROOT)
    report_python=os.environ.get('REPORT_PYTHON',sys.executable)
    subprocess.run([report_python,str(ROOT/'build_reports.py')],check=True,cwd=ROOT)
    subprocess.run([report_python,str(ROOT/'run_reports.py')],check=True,cwd=ROOT)
    print('Two reports generated. Final review and remote deployment still required.',flush=True)

if __name__=='__main__':main()
