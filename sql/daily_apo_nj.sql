WITH date_series AS (
    SELECT d::date AS "Date"
    FROM generate_series(
        (now() AT TIME ZONE 'US/Pacific')::date,
        (now() AT TIME ZONE 'US/Pacific' + INTERVAL '3 month')::date,
        '1 day'
    ) d
    WHERE EXTRACT(DOW FROM d) BETWEEN 1 AND 5
),

transformed_po AS (
    SELECT
        CASE
            WHEN EXTRACT(DOW FROM raw_date) = 6 THEN raw_date + INTERVAL '2 day'
            WHEN EXTRACT(DOW FROM raw_date) = 0 THEN raw_date + INTERVAL '1 day'
            ELSE raw_date
        END AS "Date",
        po_number,
        vendor_id
    FROM (
        SELECT
            (
                CASE
                    WHEN TRIM(vendor_id) = 'AGA' THEN a_eta
                    ELSE a_eta + INTERVAL '7 day'
                END
            )::DATE AS raw_date,
            TRIM(po_number) AS po_number,
            TRIM(vendor_id) AS vendor_id
        FROM bi.po_eta
    ) AS base
),

counted_po AS (
    SELECT
        "Date",
        COUNT(*) AS base_count,
        SUM(CASE WHEN vendor_id = 'AGA' THEN 1 ELSE 0 END) AS aga_count,
        SUM(CASE WHEN vendor_id != 'AGA' THEN 1 ELSE 0 END) AS oversea_count
    FROM transformed_po
    GROUP BY "Date"
),

final AS (
    SELECT
        ds."Date",
        COALESCE(cp.base_count, 0) AS base_count,
        COALESCE(cp.aga_count, 0) AS aga_count,
        COALESCE(cp.oversea_count, 0) AS oversea_count,
        CASE
            WHEN cp.base_count IS NULL THEN 1
            WHEN cp.aga_count = 0 THEN 1
            ELSE 0
        END AS added
    FROM date_series ds
    LEFT JOIN counted_po cp ON ds."Date" = cp."Date"
)

SELECT
    "Date",
    base_count + added AS "APO",

    -- AGA 列：如果补了1，加上 +1 forecast
    CASE
        WHEN added = 1 THEN aga_count || ' +1 Forecast'
        ELSE aga_count::text
    END AS "AGA Count",

    -- Oversea 列：保持不变
    oversea_count AS "Oversea Count"

FROM final
ORDER BY "Date";

