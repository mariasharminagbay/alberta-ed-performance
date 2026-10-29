-- Phase 5, step 3: summary views. They give reference numbers that the Power BI DAX
-- measures must match in Phase 7, and answer the triage question from Phase 3.
--
-- Weighted median / 90th percentile: sort visits by minutes, add up their weights,
-- and take the first value where the running total reaches 50% (or 90%) of the total.
-- This is the same rule clean.py uses, so the numbers should match it exactly.

-- Yearly headline figures ---------------------------------------------------
create or replace view vw_year_summary as
with wait as (
    select year, waittime_min as minutes,
           sum(weight) over (partition by year order by waittime_min, visit_id) as running,
           sum(weight) over (partition by year) as total
    from fact_ed_visit
    where waittime_min is not null
),
stay as (
    select year, lov_min as minutes,
           sum(weight) over (partition by year order by lov_min, visit_id) as running,
           sum(weight) over (partition by year) as total
    from fact_ed_visit
    where lov_min is not null
),
wait_pct as (
    select year,
           min(minutes) filter (where running >= total * 0.5) as median_wait_min,
           min(minutes) filter (where running >= total * 0.9) as p90_wait_min
    from wait group by year
),
stay_pct as (
    select year,
           min(minutes) filter (where running >= total * 0.5) as median_visit_min,
           min(minutes) filter (where running >= total * 0.9) as p90_visit_min
    from stay group by year
),
rates as (
    select
        f.year,
        count(*)                                   as sample_visits,
        round((sum(f.weight) / 1e6)::numeric, 1)   as visits_millions,
        round((100 * sum(f.weight) filter (where f.waittime_min is null) / sum(f.weight))::numeric, 1)
                                                   as wait_missing_pct,
        round((100 * sum(f.weight) filter (where o.outcome = 'Left without being seen') / sum(f.weight))::numeric, 1)
                                                   as left_without_seen_pct,
        round((100 * sum(f.weight) filter (where o.outcome = 'Admitted') / sum(f.weight))::numeric, 1)
                                                   as admitted_pct
    from fact_ed_visit f
    join dim_outcome o using (outcome_key)
    group by f.year
)
select r.year, r.sample_visits, r.visits_millions,
       w.median_wait_min, w.p90_wait_min,
       s.median_visit_min, s.p90_visit_min,
       r.wait_missing_pct, r.left_without_seen_pct, r.admitted_pct
from rates r
join wait_pct w using (year)
join stay_pct s using (year)
order by r.year;

-- Wait time by triage level, all years combined -----------------------------
-- reliable = at least 30 sample visits behind the figure (project screening rule;
-- the full NCHS standard also needs design-based confidence intervals).
create or replace view vw_triage_wait as
with wait as (
    select t.triage_group, t.triage_sort, f.waittime_min as minutes, f.weight,
           sum(f.weight) over (partition by t.triage_group order by f.waittime_min, f.visit_id) as running,
           sum(f.weight) over (partition by t.triage_group) as total
    from fact_ed_visit f
    join dim_triage t using (triage_code)
    where f.waittime_min is not null
)
select
    triage_group,
    count(*)                                                      as sample_visits,
    round((100 * sum(weight) / (select sum(weight) from fact_ed_visit where waittime_min is not null))::numeric, 1)
                                                                  as share_of_timed_visits_pct,
    min(minutes) filter (where running >= total * 0.5)            as median_wait_min,
    min(minutes) filter (where running >= total * 0.9)            as p90_wait_min,
    count(*) >= 30                                                as reliable
from wait
group by triage_group, triage_sort
order by triage_sort;
