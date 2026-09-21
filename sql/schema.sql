CREATE TABLE IF NOT EXISTS etl_days (
    sale_date date PRIMARY KEY,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    source_rows integer NOT NULL CHECK (source_rows >= 0),
    accepted_rows integer NOT NULL CHECK (accepted_rows >= 0),
    rejected_rows integer NOT NULL CHECK (rejected_rows >= 0),
    snapshot_sha256 text NOT NULL,
    CHECK (source_rows = accepted_rows + rejected_rows)
);
CREATE TABLE IF NOT EXISTS sales (
    sale_date date NOT NULL,
    row_key text NOT NULL,
    occurrence integer NOT NULL CHECK (occurrence > 0),
    client_id bigint NOT NULL CHECK (client_id > 0),
    gender text NOT NULL,
    sale_second integer NOT NULL CHECK (sale_second BETWEEN 0 AND 86399),
    product_id bigint NOT NULL CHECK (product_id > 0),
    quantity integer NOT NULL CHECK (quantity > 0),
    price_per_item numeric(18,2) NOT NULL CHECK (price_per_item >= 0),
    discount_per_item numeric(18,2) NOT NULL CHECK (discount_per_item >= 0 AND discount_per_item <= price_per_item),
    total_price numeric(20,2) NOT NULL CHECK (total_price >= 0),
    PRIMARY KEY (sale_date, row_key, occurrence)
);
CREATE TABLE IF NOT EXISTS rejected_rows (
    sale_date date NOT NULL,
    source_index integer NOT NULL,
    reason text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (sale_date, source_index)
);
CREATE INDEX IF NOT EXISTS sales_client_date_idx ON sales (client_id, sale_date);
CREATE INDEX IF NOT EXISTS sales_product_date_idx ON sales (product_id, sale_date);
CREATE OR REPLACE VIEW daily_metrics AS
SELECT sale_date, count(*) AS purchase_lines, count(DISTINCT client_id) AS active_clients,
       count(DISTINCT product_id) AS active_products, sum(quantity) AS units,
       sum(total_price) AS revenue, sum(quantity * price_per_item) AS gross_before_discount,
       sum(quantity * discount_per_item) AS discount_amount
FROM sales GROUP BY sale_date;
CREATE OR REPLACE VIEW monthly_metrics AS
SELECT date_trunc('month', sale_date)::date AS month,
       count(*) AS purchase_lines, count(DISTINCT client_id) AS active_clients,
       count(DISTINCT product_id) AS active_products, sum(quantity) AS units,
       sum(total_price) AS revenue,
       sum(total_price) / NULLIF(count(DISTINCT client_id),0) AS revenue_per_active_client
FROM sales GROUP BY 1;
