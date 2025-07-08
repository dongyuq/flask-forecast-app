WITH combined_data AS (
    SELECT
        location,
        model,
        manufacturer,
        invoice_date,
        price,
        cost,
        qty
    FROM bi.v_model_revenue_etail

    UNION ALL

    SELECT
        'NJHMLG' AS location,
        model,
        manufacturer,
        invoice_date,
        0 AS price,
        0 AS cost,
        qty
    FROM bi.v_rma_qty
    WHERE invoice_date IS NOT NULL
      AND LOWER(is_to_stock) = 'no'
)

SELECT
    -- ✅ 把 invoice_date 转换为 PST 并取日期部分
    (invoice_date AT TIME ZONE 'UTC' AT TIME ZONE 'US/Pacific')::date AS "Invoice Date",
    SUM(COALESCE(cbf_table.cbf, 0) * c.qty) AS "Total Cuft",
    SUM(price) AS "Sales",
    SUM(cost) AS "Cost"
FROM combined_data c
JOIN bi.v_model_cbf cbf_table
    ON c.model = cbf_table.model
GROUP BY (invoice_date AT TIME ZONE 'UTC' AT TIME ZONE 'US/Pacific')::date
ORDER BY "Invoice Date";
