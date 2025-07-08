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
    c.invoice_date::date AS "Invoice Date",
    SUM(COALESCE(cbf_table.cbf, 0) * c.qty) AS "Total Cuft",
    SUM(c.price) AS "Sales",
    SUM(c.cost) AS "Cost"
FROM combined_data c
LEFT JOIN bi.v_model_cbf cbf_table
    ON c.model = cbf_table.model
GROUP BY c.invoice_date::date
ORDER BY "Invoice Date";
