-- Phase 5, step 2: the fact table. One row per sampled visit, holding the measures
-- (weight and minutes) plus a key to each dimension. Foreign keys make PostgreSQL
-- reject any visit whose code has no matching dimension row.

drop table if exists fact_ed_visit cascade;
create table fact_ed_visit (
    visit_id             integer primary key,

    -- keys to dimensions
    year                 smallint not null references dim_year (year),
    triage_code          smallint not null references dim_triage (triage_code),
    outcome_key          smallint not null references dim_outcome (outcome_key),
    age_group_key        smallint not null references dim_age_group (age_group_key),
    sex_code             smallint not null references dim_sex (sex_code),
    payer_code           smallint not null references dim_payer (payer_code),
    region_code          smallint not null references dim_region (region_code),
    msa_code             smallint not null references dim_metro (msa_code),
    weekday_code         smallint not null references dim_weekday (weekday_code),
    arrival_key          smallint not null references dim_arrival_mode (arrival_key),
    hour_key             smallint not null references dim_hour (hour_key),
    reason_code          integer  not null references dim_reason (reason_code),

    -- measures
    weight               double precision not null,  -- visits this record represents nationally
    waittime_min         integer,   -- minutes to first provider; empty when not recorded
    lov_min              integer,   -- length of visit
    boarded_min          integer,   -- minutes boarded after admission decision

    -- why a measure is empty (blank / unknown / not applicable)
    waittime_missing     text,
    lov_missing          text,
    boarded_missing      text,

    -- other visit details
    age                  smallint not null,
    hospital_code        smallint not null,  -- anonymous; only meaningful within one year
    diagnosis_code       varchar(8),
    design_stratum       integer not null,   -- survey design, for error estimates only
    design_psu           integer not null
);

insert into fact_ed_visit
select
    v.visit_id,
    v.year,
    v.triage_code,
    o.outcome_key,
    a.age_group_key,
    v.sex_code,
    v.payer_code,
    v.region_code,
    v.msa_code,
    v.weekday_code,
    case v.arrived_by_ambulance when 'Yes' then 1 when 'No' then 2 else 3 end,
    coalesce(v.arrival_hour, -1),
    v.reason_code,
    v.weight,
    v.waittime_min,
    v.lov_min,
    v.boarded_min,
    v.waittime_missing,
    v.lov_missing,
    v.boarded_missing,
    v.age,
    v.hospital_code,
    v.diagnosis_code,
    v.design_stratum,
    v.design_psu
from visits_clean v
join dim_outcome   o on o.outcome   = v.outcome
join dim_age_group a on a.age_group = v.age_group;

-- Indexes on the keys Power BI filters by most
create index ix_fact_year    on fact_ed_visit (year);
create index ix_fact_triage  on fact_ed_visit (triage_code);
create index ix_fact_outcome on fact_ed_visit (outcome_key);
create index ix_fact_region  on fact_ed_visit (region_code);
