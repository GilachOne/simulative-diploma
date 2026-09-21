"""Reconcile the calendar, accepted rows and quarantine after historical loading."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from etl import connect, FIRST_DATE

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--end',type=date.fromisoformat)
    parser.add_argument('--output',type=Path,default=Path('data/history-verification.json'))
    args=parser.parse_args()
    end=args.end or datetime.now(ZoneInfo(os.getenv('BUSINESS_TIMEZONE','Europe/Moscow'))).date()-timedelta(days=1)
    connection=connect()
    try:
        connection.set_session(isolation_level='REPEATABLE READ',readonly=True)
        with connection:
            with connection.cursor() as cur:
                cur.execute("""SELECT d::date FROM generate_series(%s::date,%s::date,'1 day') d
                    LEFT JOIN etl_days e ON e.sale_date=d::date WHERE e.sale_date IS NULL ORDER BY 1""",(FIRST_DATE,end))
                missing=[str(row[0]) for row in cur.fetchall()]
                cur.execute("""WITH a AS (SELECT sale_date,count(*) n FROM sales WHERE sale_date BETWEEN %s AND %s GROUP BY 1),
                    r AS (SELECT sale_date,count(*) n FROM rejected_rows WHERE sale_date BETWEEN %s AND %s GROUP BY 1)
                    SELECT e.sale_date FROM etl_days e LEFT JOIN a USING(sale_date) LEFT JOIN r USING(sale_date)
                    WHERE e.sale_date BETWEEN %s AND %s AND
                    (e.accepted_rows<>coalesce(a.n,0) OR e.rejected_rows<>coalesce(r.n,0) OR e.source_rows<>e.accepted_rows+e.rejected_rows)
                    ORDER BY 1""",(FIRST_DATE,end,FIRST_DATE,end,FIRST_DATE,end))
                mismatched=[str(row[0]) for row in cur.fetchall()]
                cur.execute("""SELECT extract(year FROM sale_date)::int,count(*),sum(source_rows),sum(accepted_rows),sum(rejected_rows)
                    FROM etl_days WHERE sale_date BETWEEN %s AND %s GROUP BY 1 ORDER BY 1""",(FIRST_DATE,end))
                years=[dict(zip(['year','days','source_rows','accepted_rows','rejected_rows'],row)) for row in cur.fetchall()]
    finally:connection.close()
    result={'status':'complete' if not missing and not mismatched else 'incomplete',
        'checked_at':datetime.now(timezone.utc).isoformat(),'start':str(FIRST_DATE),'end':str(end),
        'expected_days':(end-FIRST_DATE).days+1,'loaded_days':sum(y['days'] for y in years),
        'missing_dates':missing,'mismatched_dates':mismatched,'years':years}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temporary=args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=int),encoding='utf-8')
    temporary.replace(args.output)
    print('History verification:',result['status'],f"{result['loaded_days']}/{result['expected_days']} days")
    return int(result['status']!='complete')

if __name__=='__main__':raise SystemExit(main())
