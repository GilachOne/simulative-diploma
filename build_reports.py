"""Build two research notebooks. Run after export_research.py."""
from pathlib import Path
import nbformat as nbf

ROOT = Path(__file__).resolve().parent
INIT = '''from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
ROOT = Path.cwd()
DATA = ROOT / 'data/research'
OUT = ROOT / 'results'
OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','figure.dpi':120,
    'axes.spines.top':False,'axes.spines.right':False})
pd.set_option('display.max_columns', 15)
pd.set_option('display.float_format',lambda x:f'{x:,.2f}')
coverage = pd.read_csv(DATA/'coverage.csv')
assert len(coverage)==365
quality = pd.read_csv(DATA/'quality_reasons.csv')
source_rows = coverage.source_rows.sum()
accepted_rows = coverage.accepted_rows.sum()
reject_rate = coverage.rejected_rows.sum()/source_rows
display(pd.DataFrame({'Показатель':['Дней API','Строк источника','Строк в анализе','Доля исключённых','Пустых ответов','Дней без принятых строк'],
    'Значение':[len(coverage),source_rows,accepted_rows,f'{reject_rate:.2%}',
    int((coverage.source_rows==0).sum()),int((coverage.accepted_rows==0).sum())]}))
display(quality)
'''
LIMITS = '''## Данные и ограничения
Источник: учебный API `http://final-project.simulative.ru/data`, по одному запросу на день. Период исследования: 01.01–31.12.2023. Сначала сохранены исходные ответы, затем проверены типы, дата, количество, скидка и равенство `total_price = quantity × (price_per_item − discount_per_item)`.

В анализ включены положительные количества с корректными реквизитами и суммой. Нулевые количества и другие ошибки строк помещены в карантин. При смешанных или пропущенных датах весь ответ API запрашивается повторно. Даты не подставляются из URL: такая подстановка могла бы приписать чужие продажи другому дню. Запросы выполняются строго последовательно после выявления дефекта параллельной выдачи API. Пустой ответ означает отсутствие строк в ответе, а не доказанное отсутствие реальных продаж. Исключения могут смещать результаты, особенно сравнения дней и месяцев.

Одна запись — товарная строка покупки. **ID заказа отсутствует**, поэтому не считаются число заказов и средний чек заказа. Валюта не описана поставщиком, суммы обозначены как **денежные единицы**. Нет названий, категорий, себестоимости, остатков, просмотров и рекламных затрат. Нельзя доказать прибыльность SKU, потерянный спрос, окупаемость привлечения или причинный эффект скидок. Данные учебные; рекомендации — проекты проверяемых решений для этого набора, а не утверждения о реальной компании.
'''

def notebook(name, sections):
    cells=[nbf.v4.new_markdown_cell(text.strip()) if kind=='md' else nbf.v4.new_code_cell(text.strip()) for kind,text in sections]
    nb=nbf.v4.new_notebook(cells=cells)
    nb.metadata.kernelspec={'display_name':'Python 3','name':'python3','language':'python'}
    nbf.write(nb,ROOT/'reports'/name)

assortment=[('md','''# Исследование 1. Ассортимент маркетплейса

## Бизнес-задача
Определить, какие товары формируют выручку, где стоит проверить глубину скидки и какие позиции требуют проверки перед выводом из ассортимента. Адресаты — категорийный менеджер и руководитель коммерческого блока.

Результат — конкретные списки SKU с правилами отбора, расчёт возможного изменения выручки и план проверки. Вывод товара или изменение цены не выполняется автоматически: для окончательного решения нужны маржа и остатки.

План: качество данных → структура продаж → ABC → стабильность помесячного спроса → кандидаты на ценовой тест → кандидаты на проверку ассортимента → рекомендации.'''),('md',LIMITS),('code',INIT),
('md','''## 1. Продажи и наблюдаемая динамика
Выручка — сумма `total_price` после скидок. Скидка — сумма скидки на единицу, умноженной на количество. Доля скидки считается от общей стоимости до скидок, а не как простое среднее процентов отдельных строк. Сравнение месяцев сопровождается долей отклонённых строк: неполный месяц не следует интерпретировать как падение спроса.'''),
('code','''products=pd.read_csv(DATA/'products.csv')
monthly=pd.read_csv(DATA/'monthly.csv',parse_dates=['month'])
products['discount_share']=products.discount_amount/products.gross.replace(0,np.nan)
products['net_unit_price']=products.revenue/products.units
assert np.isclose(products.revenue.sum(),monthly.revenue.sum())
assert int(products.purchase_lines.sum())==int(accepted_rows)
print('SKU:',len(products),'Выручка:',round(products.revenue.sum(),2),'Количество единиц:',int(products.units.sum()))
print('Взвешенная доля скидки:',round(products.discount_amount.sum()/products.gross.sum(),4))
q=coverage.assign(month=pd.to_datetime(coverage.sale_date).dt.to_period('M').astype(str)).groupby('month')[['source_rows','rejected_rows']].sum()
fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True)
axes[0].bar(monthly.month.dt.strftime('%Y-%m'),monthly.revenue/1e9,color='#178b88')
axes[0].set(ylabel='Млрд ден. ед.',title='Выручка после очистки, 2023')
axes[1].bar(q.index,100*q.rejected_rows/q.source_rows,color='#c66b44')
axes[1].set(ylabel='Исключено строк, %',xlabel='Месяц')
axes[1].tick_params(axis='x',rotation=45)
plt.tight_layout(); plt.show()'''),
('md','''## 2. ABC-анализ
Товары сортируются по выручке. Группа A включает позиции до достижения 80% накопленной выручки, B — следующие до 95%, C — остальные. Товар, пересекающий порог, остаётся в предыдущей группе: классификация опирается на накопленную долю **до** текущего товара. Нулевая выручка относится к C. Это сегментация вклада в выручку, а не маржи.'''),
('code','''products=products.sort_values(['revenue','product_id'],ascending=[False,True]).reset_index(drop=True)
products['revenue_share']=products.revenue/products.revenue.sum()
before=products.revenue_share.cumsum()-products.revenue_share
products['ABC']=np.select([(before<.8)&(products.revenue>0),(before<.95)&(products.revenue>0)],['A','B'],default='C')
abc=products.groupby('ABC').agg(skus=('product_id','size'),revenue=('revenue','sum'),units=('units','sum'))
abc['sku_share']=abc.skus/len(products)
abc['revenue_share']=abc.revenue/products.revenue.sum()
display(abc)
top=products.head(10)[['product_id','revenue','units','clients','discount_share','ABC']]
display(top)
fig,ax=plt.subplots(figsize=(9,4))
ax.plot(100*(np.arange(len(products))+1)/len(products),100*products.revenue_share.cumsum(),color='#178b88')
ax.axhline(80,ls='--',color='gray'); ax.axhline(95,ls=':',color='gray')
ax.set(xlabel='Доля SKU, %',ylabel='Накопленная доля выручки, %',title='Концентрация выручки по товарам')
plt.tight_layout(); plt.show()
abc.to_csv(OUT/'assortment_abc.csv',encoding='utf-8-sig')'''),
('md','''## 3. Стабильность и сопоставимость товаров
Для каждого SKU считаются число месяцев с продажами и коэффициент вариации месячного количества (стандартное отклонение / среднее). Неактивный месяц заполняется нулём только в пределах полного календарного 2023 года. Это ноль **наблюдаемых принятых продаж**, а не подтверждение отсутствия спроса.

Сопоставление минимальной и максимальной цены по одному ID — дополнительная проверка смысла товарного идентификатора. Очень широкий разброс может означать изменение цены, разные варианты товара или особенность генератора. Без справочника выбрать объяснение нельзя.'''),
('code','''pm=pd.read_csv(DATA/'product_months.csv',parse_dates=['month'])
pivot=pm.pivot(index='product_id',columns='month',values='units').reindex(columns=pd.date_range('2023-01-01','2023-12-01',freq='MS')).fillna(0)
products=products.join((pivot>0).sum(axis=1).rename('active_months'),on='product_id')
products=products.join((pivot.std(axis=1,ddof=0)/pivot.mean(axis=1)).rename('monthly_cv'),on='product_id')
products['list_price_ratio']=products.max_list_price/products.min_list_price.replace(0,np.nan)
display(products[['active_months','monthly_cv','list_price_ratio']].describe())
wide_price=(products.list_price_ratio>10).sum()
display(Markdown(f'У **{wide_price:,} из {len(products):,} SKU** максимальная заявленная цена более чем в 10 раз выше минимальной. Перед ценовыми решениями необходимо проверить, что один product_id действительно обозначает сопоставимый товар.'))'''),
('md','''## 4. Конкретные кандидаты для проверки скидки
Выбираются товары группы A с взвешенной скидкой не менее 50%, продажами минимум в 10 месяцах и минимум 30 покупателями за год. Отбор не доказывает избыточность скидки: он выделяет большой денежный объём, на котором небольшой проверяемый эффект был бы заметен. Порог 30 — фильтр совсем редких позиций, а не достаточный размер выборки для ценового теста.

Сценарий: уменьшить **среднюю взвешенную** скидку на 2 процентных пункта стоимости до скидок. При неизменных количестве и структуре покупок дополнительная выручка равна `0,02 × gross`. Допустимое падение количества до нулевого эффекта на выручку равно `прирост / (исходная выручка + прирост)`. Это арифметический сценарий на годовом объёме, не прогноз и не расчёт прибыли. Практический механизм акции необходимо сверить с реальными правилами скидок.'''),
('code','''candidates=products[(products.ABC=='A')&(products.discount_share>=.5)&(products.active_months>=10)&(products.clients>=30)].copy()
candidates['scenario_extra_revenue']=.02*candidates.gross
candidates['break_even_unit_loss']=candidates.scenario_extra_revenue/(candidates.revenue+candidates.scenario_extra_revenue)
candidates=candidates.sort_values('scenario_extra_revenue',ascending=False).head(10)
display(candidates[['product_id','revenue','clients','discount_share','scenario_extra_revenue','break_even_unit_loss']])
candidates.to_csv(OUT/'assortment_discount_pilot.csv',index=False,encoding='utf-8-sig')
audit=products[products.ABC=='C'].sort_values(['revenue','clients']).head(15)
display(audit[['product_id','revenue','units','clients','active_months','monthly_cv']])
audit.to_csv(OUT/'assortment_review_candidates.csv',index=False,encoding='utf-8-sig')'''),
('md','''## 5. Рекомендации категорийным менеджерам

**Первое действие — проверить справочник и качество источника.** Для выбранных SKU получить название, вариант, категорию, закупочную цену, историю прайс-листа и промо. Если ID смешивает разные варианты или даты ненадёжны, сначала исправить контракт данных. Исключённые продажи не считать потерянным спросом.

**Затем провести ценовой пилот на списке `assortment_discount_pilot.csv`.** После проверки идентификаторов выбрать первые 3 SKU из таблицы. Разделить подходящих клиентов случайно на две группы с постоянным закреплением; контроль сохраняет текущую скидку, тест уменьшает её по согласованной схеме. Основная метрика — маржинальный доход на назначенного клиента за фиксированный период. Пока себестоимость не доступна, использовать выручку на назначенного клиента только как предварительный показатель, не как доказательство прибыльности. Контролировать конверсию, возвраты и повторную покупку. Длительность и размер выборки рассчитать по клиентской дисперсии и минимально полезному эффекту до запуска; не завершать тест при первом значимом p-value. Рассчитанный порог потери количества — сценарный ориентир, а не статистическое правило остановки.

**Группу C не удалять автоматически.** Для конкретных 15 SKU из второй таблицы проверить остатки, число дней доступности, маржу и долю совместных покупок с товарами A. Низкая выручка может объясняться отсутствием товара на складе или ролью дополняющей позиции. Вывод обсуждать только при подтверждённой доступности и отрицательном экономическом вкладе. Нулевой остаток требует восстановления поставки, а не вывода позиции.

**Не расширять ассортимент по этим данным вслепую.** Без категорий, поисковых запросов и неуспешных просмотров нельзя назвать обоснованные новые позиции. Следующий сбор данных: запросы без результата, просмотры карточек, остатки, замены и товары в корзинах. Это позволит отличить отсутствующий спрос от неудовлетворённого.

### Итог в числах'''),
('code','''lines=[f'В исследовании {len(products):,} продававшихся SKU и {accepted_rows:,} принятых товарных строк; исключено {reject_rate:.2%} исходных строк.',
f'Группа A: {int(abc.loc["A","skus"]):,} SKU ({abc.loc["A","sku_share"]:.1%} ассортимента), {abc.loc["A","revenue_share"]:.1%} выручки.',
f'Для проверки глубины скидки отобрано {len(candidates)} SKU. Суммарный сценарный прирост при прежнем объёме: {candidates.scenario_extra_revenue.sum():,.0f} денежных единиц за год. Этот эффект не гарантирован.',
'Файлы с конкретными product_id и расчётами приложены; решения требуют подтверждения стоимости и идентичности товаров.']
display(Markdown('\\n\\n'.join(lines)))
products.to_csv(OUT/'assortment_products.csv',index=False,encoding='utf-8-sig')''')]

clients=[('md','''# Исследование 2. Клиентская база и повторные покупки

## Бизнес-задача
Найти направления работы с существующими клиентами: кого возвращать, кому помогать совершить следующую покупку и как измерять эффект без подмены LTV годовой выручкой.

Адресаты — CRM-менеджер и руководитель маркетплейса. Результат — сегменты с размером и денежным вкладом, когортная картина, предложения по двум контролируемым кампаниям и требования к дополнительным данным.'''),('md',LIMITS),('code',INIT),
('md','''## 1. Что можно измерить
R — число дней от последней наблюдаемой покупки до 01.01.2024. F — число **разных дней с покупками** за 2023 год, не число заказов. M — выручка после скидок за этот год. Покупкой здесь считается принятая товарная строка, включая бесплатный товар, если количество положительное.

`M / число клиентов` — наблюдаемая годовая выручка на клиента. Это не lifetime LTV: нет полного срока жизни, маржи и стоимости привлечения. Первая покупка внутри 2023 года не обязательно первая в жизни клиента. Когорты ниже называются «впервые наблюдённые в 2023», без утверждения, что это новые клиенты компании.'''),
('code','''customers=pd.read_csv(DATA/'clients.csv',parse_dates=['first_date','last_date'])
customers['recency_days']=(pd.Timestamp('2024-01-01')-customers.last_date).dt.days
customers['tenure_days']=(pd.Timestamp('2023-12-31')-customers.first_date).dt.days+1
assert customers.client_id.is_unique
monthly=pd.read_csv(DATA/'monthly.csv',parse_dates=['month'])
assert np.isclose(customers.revenue.sum(),monthly.revenue.sum())
display(customers[['revenue','purchase_days','purchase_lines','recency_days']].describe(percentiles=[.25,.5,.75,.9,.95]))
repeat_share=(customers.purchase_days>=2).mean()
display(Markdown(f'Уникальных наблюдаемых клиентов: **{len(customers):,}**. Доля с покупками в два и более разных дня: **{repeat_share:.2%}**. Выручка за 2023 год на одного клиента: **{customers.revenue.mean():,.2f} денежных единиц**.'))
fig,axes=plt.subplots(1,2,figsize=(11,4))
freq=customers.purchase_days.value_counts().sort_index()
axes[0].bar(freq.index,freq.values,color='#178b88')
axes[0].set(xlabel='Дней с покупками за год',ylabel='Клиенты',title='Частота наблюдаемой активности')
axes[1].hist(customers.recency_days,bins=24,color='#4d6b98')
axes[1].set(xlabel='Дней с последней покупки',ylabel='Клиенты',title='Давность на 01.01.2024')
plt.tight_layout();plt.show()'''),
('md','''## 2. Когорты и окно наблюдения
В каждой когорте знаменатель — число клиентов, впервые наблюдённых в данном месяце 2023 года. В ячейках — доля этих же клиентов с покупками в соответствующем последующем месяце. Это календарное месячное удержание, а не D30. Будущие для когорты месяцы оставлены пустыми, а не заполнены нулями.

Декабрьскую когорту нельзя сравнивать с январской по годовому M: у них разная длительность наблюдения. Для отдельной метрики возврата за 60 дней берутся только клиенты с первой наблюдаемой покупкой не позднее 01.11.2023. Возврат означает другой день покупки в пределах последующих 60 дней. Ошибки исходных дат могут занижать показатель.'''),
('code','''cohorts=pd.read_csv(DATA/'cohorts.csv',parse_dates=['cohort','activity_month'])
cohorts['age_month']=(cohorts.activity_month.dt.year-cohorts.cohort.dt.year)*12+cohorts.activity_month.dt.month-cohorts.cohort.dt.month
base=cohorts.loc[cohorts.age_month==0].set_index('cohort').active_clients
cohorts['retention']=cohorts.active_clients/cohorts.cohort.map(base)
retention=cohorts.pivot(index='cohort',columns='age_month',values='retention').reindex(columns=range(12))
for cohort in retention.index:
    last_age=12-cohort.month
    retention.loc[cohort,range(last_age+1)]=retention.loc[cohort,range(last_age+1)].fillna(0)
display(retention)
fig,ax=plt.subplots(figsize=(11,5))
image=ax.imshow(retention.values*100,cmap='YlGnBu',vmin=0,vmax=100,aspect='auto')
ax.set_xticks(range(12),range(12));ax.set_yticks(range(len(retention)),retention.index.strftime('%Y-%m'))
ax.set(xlabel='Месяцев после первого наблюдения в 2023',ylabel='Когорта',title='Календарное удержание, %')
for i in range(len(retention)):
 for j in range(12):
  val=retention.iloc[i,j]
  if pd.notna(val):ax.text(j,i,f'{100*val:.0f}',ha='center',va='center',fontsize=8,color='white' if val>.55 else 'black')
fig.colorbar(image,ax=ax);plt.tight_layout();plt.show()
r60=pd.read_csv(DATA/'repeat_60.csv').iloc[0]
display(Markdown(f'Из **{int(r60.eligible_clients):,}** клиентов с полным 60-дневным окном вернулись **{int(r60.returned_clients):,}**, то есть **{r60.returned_clients/r60.eligible_clients:.2%}**. Это описание наблюдаемых данных, не причинный эффект CRM.'))
retention.to_csv(OUT/'clients_retention.csv',encoding='utf-8-sig')'''),
('md','''## 3. Практические сегменты
Правила выбираются до расчёта итогов кампаний, на срезе 01.01.2024. Порог высокой денежной ценности — 75-й перцентиль годового M. Это рабочие правила для пилота, а не статистически оптимальные границы.

- «Вернуть ценных»: M не ниже порога, не менее двух дней с покупками и последняя покупка 90 или более дней назад.
- «Активные ценные»: M не ниже порога, минимум три дня с покупками и R ≤ 30.
- «Недавние однократные»: один день с покупками, R ≤ 30.
- «Остальные»: все другие наблюдаемые клиенты.

Сегменты взаимоисключающие. Нельзя называть всех давно не покупавших ушедшими: нет договорного признака оттока и срока обычного цикла покупки.'''),
('code','''threshold=customers.revenue.quantile(.75)
conditions=[(customers.revenue>=threshold)&(customers.purchase_days>=2)&(customers.recency_days>=90),
 (customers.revenue>=threshold)&(customers.purchase_days>=3)&(customers.recency_days<=30),
 (customers.purchase_days==1)&(customers.recency_days<=30)]
labels=['Вернуть ценных','Активные ценные','Недавние однократные']
customers['segment']=np.select(conditions,labels,default='Остальные')
segments=customers.groupby('segment').agg(clients=('client_id','size'),revenue=('revenue','sum'),
    mean_purchase_days=('purchase_days','mean'),median_recency=('recency_days','median'))
segments['client_share']=segments.clients/len(customers)
segments['revenue_share']=segments.revenue/customers.revenue.sum()
segments['revenue_per_client']=segments.revenue/segments.clients
print('Порог M, 75-й перцентиль:',round(threshold,2))
display(segments)
assert segments.clients.sum()==len(customers)
segments.to_csv(OUT/'clients_segments.csv',encoding='utf-8-sig')
# Individual client lists stay in excluded local data, not in the public report.
customers[['client_id','segment']].to_csv(DATA/'client_segments_private.csv',index=False)
fig,ax=plt.subplots(figsize=(9,4))
segments[['client_share','revenue_share']].mul(100).plot.barh(ax=ax,color=['#4d6b98','#178b88'])
ax.set(xlabel='Доля, %',ylabel='',title='Размер и денежный вклад сегментов');ax.legend(['Доля клиентов','Доля выручки'])
plt.tight_layout();plt.show()'''),
('md','''## 4. Две конкретные CRM-проверки

### Кампания A: вернуть ценных клиентов
Целевая группа — сегмент «Вернуть ценных» из таблицы выше. Перед запуском обновить срез на дату кампании, проверить доступность контакта и согласие на коммуникацию. В имеющихся данных контактов и согласий нет; сейчас сформирован только аналитический список ID.

Предложение пилота: персональная подборка из ранее купленных SKU, доступных сейчас, с напоминанием без дополнительной скидки. Контроль — обычное обслуживание без этой коммуникации. Случайное назначение на уровне клиента, 50/50, один клиент закрепляется в одной группе. Основная метрика — доля клиентов с покупкой в следующие 30 дней. Дополнительные — выручка и маржинальный доход на всех назначенных клиентов, отписки, жалобы и возвраты. Не анализировать только открывших сообщение или только купивших: это разрушает случайность сравнения.

### Кампания B: вторая покупка у недавних однократных
Целевая группа — «Недавние однократные». На 7-й день после первого наблюдаемого дня покупки, если повторной покупки ещё нет, протестировать подборку дополняющих товаров по истории совместных покупок. Для исторического среза это предложение механики, а не уже выполненная кампания. В текущем API нет заказа и товарных категорий: перед запуском нужен товарный справочник и события корзины, чтобы не подбирать случайные ID.

Основная метрика — повторный день покупки в течение 30 дней после назначения. Защитные метрики — маржинальный доход на клиента, отписки и возвраты. Измерять эффект по всем назначенным клиентам; учитывать клиентов без покупки как нулевой результат.

Для обеих кампаний размер выборки считается до запуска по базовой конверсии подходящего сегмента и минимально полезному приросту. Исторический показатель возврата за 60 дней не подставляется как готовая 30-дневная конверсия кампании: окна и аудитории различаются. Разделить аудитории двух тестов или учесть пересечение в дизайне.

### Как оценить денежный масштаб без обещания результата
Ниже сценарий: в каждом сегменте доля повторно купивших увеличилась на 1 процентный пункт. Сначала рассчитывается дополнительное число клиентов. Денежный эквивалент использует среднюю историческую выручку на клиентский день покупки всей базы. Это грубая иллюстрация: возвращённые клиенты могут иметь другой размер покупки. Из выручки ещё нужно вычесть себестоимость, расходы кампании и скидки; их нет в источнике.'''),
('code','''revenue_per_client_day=customers.revenue.sum()/customers.purchase_days.sum()
scenario=segments.loc[segments.index.isin(['Вернуть ценных','Недавние однократные']),['clients']].copy()
scenario['assumed_lift_pp']=1.0
scenario['extra_returning_clients']=scenario.clients*.01
scenario['illustrative_extra_revenue']=scenario.extra_returning_clients*revenue_per_client_day
display(scenario)
scenario.to_csv(OUT/'clients_scenarios.csv',encoding='utf-8-sig')
display(Markdown(f'Историческая выручка на клиентский день покупки: **{revenue_per_client_day:,.2f} денежных единиц**. Это не средний чек заказа и не прогноз выручки кампании.'))'''),
('md','''## 5. Что увеличивать и как связать это с LTV
Приоритет — **дополнительный маржинальный доход на клиента**, а не число рассылок, скидок или товарных строк. Повторная покупка полезна, если её вклад перекрывает стоимость стимулирования и не заменяет покупку, которая произошла бы без кампании. Именно для этого нужен контроль.

Для полноценного LTV добавить: дату привлечения и источник, стоимость привлечения, ID заказа, себестоимость, возвраты, затраты доставки и CRM, полную историю клиента. После этого строить накопленный маржинальный доход когорт на одинаковом возрасте и учитывать неполное наблюдение молодых когорт. Экстраполировать один год выручки на произвольное число лет нельзя.

Метрики мониторинга: активные клиенты за месяц; повторный день покупки в фиксированном окне; выручка и затем маржинальный доход на клиента; возраст когорты; доля исключённых строк; полнота календаря загрузки. Внедрять одновременно крупные изменения цен и CRM без раздельного дизайна не стоит: станет трудно объяснить результат.

## Итог
Сформированы конкретные взаимоисключающие сегменты и два проекта кампаний с аудиторией, механикой, контрольной группой и метриками. Численность и денежный вклад находятся в `clients_segments.csv`, сценарные расчёты — в `clients_scenarios.csv`. Ни один сценарий не представлен как измеренный эффект: эксперименты не проводились.

Ограничения: ошибки исходных дат, наблюдение только 2023 года, неизвестная история до окна, отсутствие контактов и себестоимости. Главный следующий шаг — связать очищенные покупки с надёжным справочником клиентов и заказов, затем проверить кампании на обновлённых данных.''')]

if __name__=='__main__':
    (ROOT/'reports').mkdir(exist_ok=True)
    notebook('01_assortment.ipynb',assortment)
    notebook('02_clients.ipynb',clients)
    print('Two research notebooks built')
