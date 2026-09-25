"""Create or update the local diploma dashboard through Metabase's documented API.

Reads private data/local-config.json; does not print credentials or session tokens.
"""
from pathlib import Path
import json
import os
import urllib.request

ROOT=Path(__file__).resolve().parent
BASE=os.getenv('METABASE_URL','http://127.0.0.1:3030').rstrip('/')
session=None

def api(method,path,payload=None):
    headers={'Content-Type':'application/json'}
    if session: headers['X-Metabase-Session']=session
    request=urllib.request.Request(BASE+path, data=json.dumps(payload).encode() if payload is not None else None,
                                  headers=headers,method=method)
    with urllib.request.urlopen(request,timeout=180) as response:
        body=response.read()
        return json.loads(body) if body else None

def main():
    global session
    cfg=json.loads((ROOT/'data/local-config.json').read_text('utf-8'))
    properties=api('GET','/api/session/properties')
    if properties.get('setup-token'):
        result=api('POST','/api/setup',{'token':properties['setup-token'],
            'user':{'email':cfg['metabase_admin_email'],'password':cfg['metabase_admin_password'],
                    'first_name':'Диплом','last_name':'Simulative'},
            'prefs':{'site_name':'Диплом · Маркетплейс','site_locale':'ru'}})
        session=result['id']
    else:
        session=api('POST','/api/session',{'username':cfg['metabase_admin_email'],
                    'password':cfg['metabase_admin_password']})['id']
    statepath=ROOT/'data/metabase-state.json'
    state=json.loads(statepath.read_text('utf-8')) if statepath.exists() else {}
    if not state.get('database_id'):
        result=api('POST','/api/database',{'name':'Маркетплейс · проверенные продажи','engine':'postgres',
            'details':{'host':cfg['loader_env']['PGHOST'],'port':int(cfg['loader_env']['PGPORT']),
                'dbname':'marketplace_diploma','user':'diploma_reader','password':cfg['reader_password'],'ssl':False},
            'is_full_sync':False,'auto_run_queries':True})
        state['database_id']=result['id']
        statepath.write_text(json.dumps(state),encoding='utf-8')
    parameters=[{'id':k,'name':n,'slug':k,'type':'date/single','default':d}
        for k,n,d in [('start_date','Начало периода','2023-01-01'),('end_date','Конец периода','2023-12-31')]]
    if not state.get('dashboard_id'):
        result=api('POST','/api/dashboard',{'name':'Маркетплейс · продажи, клиенты и качество',
            'description':'Учебный API. Денежные единицы источника. Строки не равны заказам; исключения показаны отдельно. Проверяйте число загруженных дней перед выводами.',
            'parameters':parameters})
        state['dashboard_id']=result['id']
        statepath.write_text(json.dumps(state),encoding='utf-8')
    where='sale_date BETWEEN {{start_date}} AND {{end_date}}'
    cards=[
        ('Выручка после скидок','scalar',f'SELECT sum(total_price) AS revenue FROM sales WHERE {where}',{},0,0,6,4),
        ('Активные клиенты','scalar',f'SELECT count(DISTINCT client_id) AS clients FROM sales WHERE {where}',{},0,6,6,4),
        ('Товары с продажами','scalar',f'SELECT count(DISTINCT product_id) AS products FROM sales WHERE {where}',{},0,12,6,4),
        ('Загружено дней API','scalar',f'SELECT count(*) AS loaded_days FROM etl_days WHERE {where}',{},0,18,6,4),
        ('Выручка по месяцам','line',f"SELECT date_trunc('month',sale_date) AS month,sum(total_price) AS revenue FROM sales WHERE {where} GROUP BY 1 ORDER BY 1",{'graph.dimensions':['month'],'graph.metrics':['revenue']},4,0,12,7),
        ('Активные клиенты по месяцам','bar',f"SELECT date_trunc('month',sale_date) AS month,count(DISTINCT client_id) AS clients FROM sales WHERE {where} GROUP BY 1 ORDER BY 1",{'graph.dimensions':['month'],'graph.metrics':['clients']},4,12,12,7),
        ('Топ-10 SKU по выручке','bar',f'SELECT product_id::text AS sku,sum(total_price) AS revenue FROM sales WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 10',{'graph.dimensions':['sku'],'graph.metrics':['revenue'],'graph.x_axis.scale':'ordinal'},11,0,12,7),
        ('Исключения по причинам','table',f'SELECT reason AS причина,count(*) AS rejected_lines FROM rejected_rows WHERE {where} GROUP BY 1 ORDER BY 2 DESC',{},11,12,12,7),
        ('Доля скидки от суммы до скидок, %','scalar',f'SELECT 100.0*sum(quantity*discount_per_item)/nullif(sum(quantity*price_per_item),0) AS discount_percent FROM sales WHERE {where}',{},18,0,6,4),
        ('Исключено строк источника, %','scalar',f'SELECT 100.0*sum(rejected_rows)/nullif(sum(source_rows),0) AS rejected_percent FROM etl_days WHERE {where}',{},18,6,6,4),
        ('Товарные строки покупки','scalar',f'SELECT count(*) AS purchase_lines FROM sales WHERE {where}',{},18,12,6,4),
        ('Ожидается дней в периоде','scalar','SELECT ({{end_date}}::date-{{start_date}}::date+1) AS expected_days',{},18,18,6,4),
        ('Контроль ежедневных загрузок','table',f'SELECT sale_date AS дата,source_rows AS исходных_строк,accepted_rows AS принятых_строк,rejected_rows AS отклонённых_строк,fetched_at AS время_загрузки FROM etl_days WHERE {where} ORDER BY sale_date DESC',{},22,0,24,8)
    ]
    # Keep question IDs stable when changing their presentation.
    old_names = {
        'Выручка по месяцам': 'Динамика выручки по месяцам',
        'Выручка после скидок': 'Выручка после скидок, млрд ден. ед.',
        'Активные клиенты по месяцам': 'Уникальные клиенты по месяцам',
    }
    aliases = {'revenue':'Выручка', 'clients':'Клиенты', 'products':'SKU',
        'loaded_days':'Загружено дней', 'month':'Месяц', 'sku':'SKU',
        'discount_percent':'Доля скидки, %', 'rejected_percent':'Исключено, %',
        'purchase_lines':'Товарные строки', 'expected_days':'Ожидается дней',
        'rejected_lines':'Исключено строк'}
    import re
    revised=[]
    scalar_index=0
    for name,display,query,viz,row,col,sx,sy in cards:
        if name in old_names:
            renamed=old_names[name]
            if name in state.get('cards',{}):
                state['cards'][renamed]=state['cards'][name]
            name=renamed
        query=re.sub(r'\bAS (\w+)', lambda m:'AS "'+aliases.get(m[1],m[1])+'"',query)
        viz=dict(viz)
        for key in ['graph.dimensions','graph.metrics']:
            if key in viz: viz[key]=[aliases.get(v,v) for v in viz[key]]
        if display=='scalar':
            row,col,sx,sy=(scalar_index//4)*3,(scalar_index%4)*6,6,3
            scalar_index+=1
            viz.update({'scalar.decimals':2})
            column_name=re.search(r'AS "([^"]+)"',query).group(1)
            viz['column_settings']={json.dumps(['name',column_name],ensure_ascii=False,separators=(',',':')):
                {'decimals':2 if 'Выручка'==column_name or '%' in column_name else 0,
                 **({'scale':1e-9,'number_separators':', '} if column_name=='Выручка' else {})}}
        elif display in ('line','bar'):
            viz.update({'graph.x_axis.title_text':'','graph.y_axis.title_text':
                'Клиенты' if 'клиенты по' in name else 'Денежные единицы',
                'graph.colors':['#178b88','#d58a30']})
            row=6 if 'месяцам' in name else 13
        revised.append((name,display,query,viz,row,col,sx,sy))
    cards=revised
    for i,c in enumerate(cards):
        if c[0]=='Динамика выручки по месяцам':
            query="""WITH calendar AS (
                SELECT generate_series(date_trunc('month',{{start_date}}::date),
                    date_trunc('month',{{end_date}}::date),interval '1 month') AS month
            ), amounts AS (
                SELECT date_trunc('month',sale_date) AS month,sum(total_price) AS revenue
                FROM sales WHERE sale_date BETWEEN {{start_date}} AND {{end_date}} GROUP BY 1
            ), monthly AS (
                SELECT c.month,coalesce(a.revenue,0) AS revenue FROM calendar c LEFT JOIN amounts a USING(month)
            ) SELECT month AS "Месяц",revenue AS "Выручка",
                CASE WHEN count(*) OVER w=3 THEN avg(revenue) OVER w END AS "Среднее за 3 предыдущих месяца"
                FROM monthly WINDOW w AS (ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)
                ORDER BY month"""
            viz={**c[3],'graph.metrics':['Выручка','Среднее за 3 предыдущих месяца']}
            cards[i]=(c[0],c[1],query,viz,*c[4:])
    cards.extend([
        ('Точная выручка за выбранный период','table',f'SELECT sum(total_price) AS "Выручка, ден. ед." FROM sales WHERE {where}',{},16,0,24,4),
        ('Антитоп-10 SKU по выручке','bar',f'SELECT product_id::text AS "SKU",sum(total_price) AS "Выручка" FROM sales WHERE {where} GROUP BY 1 ORDER BY 2,1 LIMIT 10',
         {'graph.dimensions':['SKU'],'graph.metrics':['Выручка'],'graph.x_axis.scale':'ordinal','graph.y_axis.title_text':'Денежные единицы','graph.colors':['#178b88']},13,12,12,7),
        ('Топ-10 SKU по количеству проданных единиц','bar',f'SELECT product_id::text AS "SKU",sum(quantity) AS "Продано единиц" FROM sales WHERE {where} GROUP BY 1 ORDER BY 2 DESC,1 LIMIT 10',
         {'graph.dimensions':['SKU'],'graph.metrics':['Продано единиц'],'graph.x_axis.scale':'ordinal','graph.y_axis.title_text':'Единицы товара','graph.colors':['#4d6b98']},20,0,24,7)
    ])
    current=api('GET',f"/api/dashboard/{state['dashboard_id']}")
    backup=ROOT/'data/dashboard-before-review.json'
    if not backup.exists(): backup.write_text(json.dumps(current,ensure_ascii=False),encoding='utf-8')
    tabs=current.get('tabs') or [{'id':-1,'name':'Продажи и клиенты','position':0},
                                {'id':-2,'name':'Качество загрузок','position':1}]
    if len(tabs)!=2: raise ValueError('Expected two dashboard tabs')
    tab_ids=[t['id'] for t in tabs]
    state.setdefault('cards',{})
    dashcards=[]
    for name,display,query,viz,row,col,sx,sy in cards:
        tags={p['id']:{'id':p['id'],'name':p['id'],'display-name':p['name'],
                       'type':'date','required':True,'default':p['default']} for p in parameters}
        body={'name':name,'display':display,'visualization_settings':viz,
              'dataset_query':{'database':state['database_id'],'type':'native','native':{'query':query,'template-tags':tags}}}
        if name in state['cards']:
            card=api('PUT',f"/api/card/{state['cards'][name]}",body)
        else:
            card=api('POST','/api/card',body)
            state['cards'][name]=card['id']
            statepath.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
        quality=name in ('Исключения по причинам','Контроль ежедневных загрузок','Точная выручка за выбранный период')
        if quality:
            row,col,sx,sy={'Исключения по причинам':(0,0,24,6),'Контроль ежедневных загрузок':(6,0,24,10),'Точная выручка за выбранный период':(16,0,24,4)}[name]
        dashcards.append({'id':-len(dashcards)-1,'card_id':card['id'],'row':row,'col':col,
            'dashboard_tab_id':tab_ids[1 if quality else 0],
            'size_x':sx,'size_y':sy,'parameter_mappings':[{'parameter_id':p['id'],
            'card_id':card['id'],'target':['variable',['template-tag',p['id']]]} for p in parameters]})
    api('PUT',f"/api/dashboard/{state['dashboard_id']}",{'dashcards':dashcards,'tabs':tabs,'parameters':parameters,'width':'full',
        'name':'Маркетплейс · продажи и клиенты',
        'description':'Учебные данные. Суммы в денежных единицах. Среднее — за 3 предыдущих месяца выбранного периода; крайние месяцы могут быть неполными. Антитоп включает только SKU с наблюдаемыми продажами: перед выводом товара проверьте маржу, остатки и сезонность.'})
    print('Dashboard ready:',BASE+'/dashboard/'+str(state['dashboard_id']))

if __name__=='__main__':main()
