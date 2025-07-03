WITH date_series AS (
    SELECT d::date AS "Date"
    FROM generate_series(current_date, current_date + INTERVAL '3 month', '1 day') d
    WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5  -- 周一到周五
),

transformed_po AS (
    SELECT
        CAST(
            CASE
                WHEN po_number LIKE 'A%' THEN a_eta
                ELSE a_eta + INTERVAL '7 day'
            END AS DATE
        ) AS "Date",
        po_number
    FROM bi.po_eta
),

counted_po AS (
    SELECT
        "Date",
        COUNT(*) AS base_count,
        SUM(CASE WHEN po_number NOT LIKE 'A%' THEN 1 ELSE 0 END) AS non_A_count
    FROM transformed_po
    GROUP BY "Date"
)

SELECT
    ds."Date",
    COALESCE(cp.base_count, 0) +
    CASE
        WHEN cp.base_count IS NULL THEN 1             -- 没有任何记录，补1
        WHEN cp.non_A_count = cp.base_count THEN 1    -- 全是非A开头，补1
        ELSE 0
    END AS "APO"
FROM date_series ds
LEFT JOIN counted_po cp ON ds."Date" = cp."Date"
ORDER BY ds."Date";
