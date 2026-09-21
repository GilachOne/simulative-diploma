"""Export aggregate 2023 research tables; no customer-level files in public output."""
from pathlib import Path
import csv
import json
from datetime import date
from etl import connect

ROOT = Path(__file__).resolve().parent
QUERIES = {
    'coverage': """SELECT sale_date,source_rows,accepted_rows,rejected_rows,snapshot_sha256
        FROM etl_days WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' ORDER BY sale_date""",
    'quality_reasons': """SELECT reason,count(*) AS rows FROM rejected_rows
        WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' GROUP BY reason ORDER BY rows DESC""",
    'monthly': """SELECT * FROM monthly_metrics WHERE month BETWEEN '2023-01-01' AND '2023-12-01' ORDER BY month""",
    'products': """SELECT product_id,count(*) AS purchase_lines,sum(quantity) AS units,
        count(DISTINCT client_id) AS clients,count(DISTINCT sale_date) AS active_days,
        sum(total_price) AS revenue,sum(quantity*price_per_item) AS gross,
        sum(quantity*discount_per_item) AS discount_amount,
        min(price_per_item) AS min_list_price,max(price_per_item) AS max_list_price
        FROM sales WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31'
        GROUP BY product_id ORDER BY revenue DESC,product_id""",
    'product_months': """SELECT product_id,date_trunc('month',sale_date)::date AS month,
        sum(total_price) AS revenue,sum(quantity) AS units FROM sales
        WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' GROUP BY 1,2 ORDER BY 1,2""",
    'clients': """SELECT client_id,min(sale_date) AS first_date,max(sale_date) AS last_date,
        count(*) AS purchase_lines,count(DISTINCT sale_date) AS purchase_days,
        sum(total_price) AS revenue,sum(quantity*discount_per_item) AS discount_amount
        FROM sales WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31'
        GROUP BY client_id ORDER BY client_id""",
    'cohorts': """WITH firsts AS (SELECT client_id,date_trunc('month',min(sale_date))::date AS cohort
        FROM sales WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' GROUP BY client_id)
        SELECT f.cohort,date_trunc('month',s.sale_date)::date AS activity_month,
        count(DISTINCT s.client_id) AS active_clients,sum(s.total_price) AS revenue
        FROM sales s JOIN firsts f USING(client_id)
        WHERE s.sale_date BETWEEN '2023-01-01' AND '2023-12-31'
        GROUP BY 1,2 ORDER BY 1,2""",
    'daily': """SELECT * FROM daily_metrics WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' ORDER BY sale_date""",
    'repeat_60': """WITH firsts AS (SELECT client_id,min(sale_date) AS first_date FROM sales
        WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31' GROUP BY client_id),
        clients AS (SELECT f.client_id, bool_or(s.sale_date>f.first_date AND s.sale_date<=f.first_date+60) AS returned
        FROM firsts f JOIN sales s USING(client_id)
        WHERE f.first_date <= '2023-11-01' AND s.sale_date BETWEEN '2023-01-01' AND '2023-12-31'
        GROUP BY f.client_id)
        SELECT count(*) AS eligible_clients,count(*) FILTER (WHERE returned) AS returned_clients FROM clients"""
}

def main():
    out = ROOT / 'data/research'
    out.mkdir(parents=True, exist_ok=True)
    connection = connect()
    try:
        with connection:
            with connection.cursor() as cur:
                cur.execute("SELECT count(*) FROM etl_days WHERE sale_date BETWEEN '2023-01-01' AND '2023-12-31'")
                if cur.fetchone()[0] != 365:
                    raise RuntimeError('Research export requires all 365 API days, including explicit empty days')
                for name, query in QUERIES.items():
                    cur.execute(query)
                    with (out/(name+'.csv')).open('w', encoding='utf-8-sig', newline='') as f:
                        writer=csv.writer(f)
                        writer.writerow([d[0] for d in cur.description])
                        while True:
                            rows=cur.fetchmany(10000)
                            if not rows: break
                            writer.writerows(rows)
                    print(name, 'exported', flush=True)
    finally:
        connection.close()

if __name__ == '__main__': main()
