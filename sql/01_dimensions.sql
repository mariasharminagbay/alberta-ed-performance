-- Phase 5, step 1: dimension tables (the "who / when / where / why" of each visit).
-- Built from the lookup tables loaded in Phase 4 plus a few fixed lists.
-- Safe to re-run: the fact table and views are dropped first because they depend on these tables.

drop table if exists fact_ed_visit cascade;

-- Year -------------------------------------------------------------------
drop table if exists dim_year cascade;
create table dim_year (
    year              smallint primary key,
    year_label        text not null,
    is_pandemic_year  boolean not null,
    note              text
);
insert into dim_year
select distinct
    year,
    year::text,
    year in (2020, 2021),
    case year
        when 2020 then 'COVID-19 year: fewest sampled visits; interpret trends with care'
        when 2021 then 'COVID-19 recovery year'
    end
from visits_clean;

-- Triage level ------------------------------------------------------------
drop table if exists dim_triage cascade;
create table dim_triage (
    triage_code   smallint primary key,
    triage_label  text not null,   -- CDC wording
    triage_group  text not null,   -- what the report shows
    triage_sort   smallint not null,
    is_triaged    boolean not null
);
insert into dim_triage
select
    code,
    label,
    case
        when code between 1 and 5 then code || ' - ' || label
        when code in (0, 7)        then 'No triage'
        else 'Unknown'
    end,
    case when code between 1 and 5 then code when code in (0, 7) then 6 else 7 end,
    code between 1 and 5
from lkp_triage;

-- Outcome (one per visit, set in clean.py) --------------------------------
drop table if exists dim_outcome cascade;
create table dim_outcome (
    outcome_key   smallint primary key,
    outcome       text not null unique,
    outcome_sort  smallint not null,
    saw_provider  boolean not null
);
insert into dim_outcome values
    (1, 'Discharged or other',         1, true),
    (2, 'Admitted',                    2, true),
    (3, 'Left against medical advice', 3, true),
    (4, 'Left without being seen',     4, false);

-- Age group (matches CIHI's groups for the Alberta comparison) ------------
drop table if exists dim_age_group cascade;
create table dim_age_group (
    age_group_key  smallint primary key,
    age_group      text not null unique,
    age_sort       smallint not null
);
insert into dim_age_group values
    (1, '0-19', 1), (2, '20-44', 2), (3, '45-64', 3), (4, '65+', 4);

-- Sex ---------------------------------------------------------------------
drop table if exists dim_sex cascade;
create table dim_sex (
    sex_code  smallint primary key,
    sex       text not null
);
insert into dim_sex select code, label from lkp_sex;

-- Payer (expected source of payment) --------------------------------------
drop table if exists dim_payer cascade;
create table dim_payer (
    payer_code   smallint primary key,
    payer_label  text not null,   -- CDC wording
    payer_group  text not null,   -- shorter groups for charts
    payer_sort   smallint not null
);
insert into dim_payer
select
    code,
    label,
    case code
        when 1 then 'Private insurance'
        when 2 then 'Medicare'
        when 3 then 'Medicaid / CHIP'
        when 5 then 'Self-pay or no charge'
        when 6 then 'Self-pay or no charge'
        when 4 then 'Other'
        when 7 then 'Other'
        else 'Unknown'
    end,
    case code when 1 then 1 when 2 then 2 when 3 then 3 when 5 then 4 when 6 then 4
              when 4 then 5 when 7 then 5 else 6 end
from lkp_payer;

-- Region and metro status -------------------------------------------------
drop table if exists dim_region cascade;
create table dim_region (
    region_code  smallint primary key,
    region       text not null
);
insert into dim_region select code, label from lkp_region;

drop table if exists dim_metro cascade;
create table dim_metro (
    msa_code      smallint primary key,
    metro_status  text not null
);
insert into dim_metro
select code, case code when 1 then 'Metro' when 2 then 'Non-metro' end
from lkp_metro;

-- Weekday -----------------------------------------------------------------
drop table if exists dim_weekday cascade;
create table dim_weekday (
    weekday_code   smallint primary key,
    weekday        text not null,
    weekday_short  text not null,
    is_weekend     boolean not null
);
insert into dim_weekday
select code, label, left(label, 3), code in (1, 7)   -- 1 = Sunday, 7 = Saturday
from lkp_weekday;

-- Arrival mode ------------------------------------------------------------
drop table if exists dim_arrival_mode cascade;
create table dim_arrival_mode (
    arrival_key   smallint primary key,
    arrival_mode  text not null,
    arrival_sort  smallint not null
);
insert into dim_arrival_mode values
    (1, 'Ambulance', 1), (2, 'Walk-in or other', 2), (3, 'Unknown', 3);

-- Arrival hour (key -1 = time not recorded) -------------------------------
drop table if exists dim_hour cascade;
create table dim_hour (
    hour_key    smallint primary key,
    hour_label  text not null,
    shift       text not null,
    shift_sort  smallint not null
);
insert into dim_hour
select
    h,
    lpad(h::text, 2, '0') || ':00',
    case when h < 8 then 'Night (00-07)' when h < 16 then 'Day (08-15)' else 'Evening (16-23)' end,
    case when h < 8 then 3 when h < 16 then 1 else 2 end
from generate_series(0, 23) as h;
insert into dim_hour values (-1, 'Unknown', 'Unknown', 4);

-- Reason for visit (module = first digit of the code, per the 2022 codebook) --
drop table if exists dim_reason cascade;
create table dim_reason (
    reason_code  integer primary key,
    reason       text not null,
    module_code  smallint not null,
    module       text not null
);
insert into dim_reason
select
    code,
    label,
    case when code < 0 then 9 else code / 10000 end,
    case when code < 0 then 'Blank'
         else case code / 10000
            when 1 then 'Symptom'
            when 2 then 'Disease'
            when 3 then 'Diagnostic, screening, preventive'
            when 4 then 'Treatment'
            when 5 then 'Injury or adverse effect'
            when 6 then 'Test results'
            when 7 then 'Administrative'
            when 8 then 'Uncodable'
            else 'Blank'
         end
    end
from lkp_reason;
