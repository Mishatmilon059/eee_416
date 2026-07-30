-- Bangla Braille Tutor -- Supabase schema
-- Paste into the Supabase SQL editor and run. Idempotent; safe to re-run.
--
-- One flat table. Deliberately flat, not normalized: the whole point of this
-- table is that `select * from attempts` IS the training CSV. Every join you
-- would have to write later is a chance for the dataset to drift.

create table if not exists attempts (
  id                bigserial primary key,
  created_at        timestamptz not null default now(),

  -- who / when -----------------------------------------------------------
  user_id           text        not null,   -- anonymous participant code, e.g. 'P01'
  session_id        text        not null,   -- uuid generated client-side
  device_id         text        not null,   -- distinguishes the two laptops
  attempt_index     integer     not null,   -- 0-based within the session

  -- the 14 model input features (order matches spec/engine_spec.json) ------
  -- All describe state AFTER this attempt was scored. See the spec's
  -- _feature_timing_contract: current_streak>0 => correct, wrong_streak>0 => wrong.
  char_id                   smallint         not null,
  response_time             double precision not null,  -- ms
  press_duration            double precision not null,  -- ms
  retry_count               smallint         not null,
  prev_accuracy             double precision not null,  -- 0..1
  prev_mastery              double precision not null,  -- 0..1
  hint_count                smallint         not null,
  session_number            smallint         not null,
  difficulty_level          smallint         not null,  -- 1..5
  time_since_last_practice  double precision not null,  -- seconds
  prev_confidence           smallint         not null,  -- 0 CONF, 1 HESIT, 2 GUESS
  current_streak            smallint         not null,
  wrong_streak              smallint         not null,
  prev_mistakes             smallint         not null,

  -- labels (rule-engine generated at collection time) ---------------------
  teaching_action   smallint    not null,   -- 0..5
  confidence_state  smallint    not null,   -- 0..2

  -- raw ground truth, kept for auditing and re-labelling ------------------
  expected_pattern  smallint    not null,   -- 6-bit dot mask
  entered_pattern   smallint    not null,
  is_correct        boolean     not null,
  press_order       text,                   -- JSON array, e.g. '[1,4,2]'

  -- provenance -----------------------------------------------------------
  source              text     not null default 'web',   -- web | esp32 | synthetic
  is_synthetic        boolean  not null default false,
  spec_version        integer  not null default 1,
  braille_map_verified boolean not null default false,

  constraint attempts_char_id_range     check (char_id between 0 and 49),
  constraint attempts_teaching_range    check (teaching_action between 0 and 5),
  constraint attempts_confidence_range  check (confidence_state between 0 and 2),
  constraint attempts_difficulty_range  check (difficulty_level between 1 and 5),
  constraint attempts_source_valid      check (source in ('web','esp32','synthetic')),
  -- enforces the timing contract: exactly one streak is non-zero after scoring
  constraint attempts_streak_exclusive  check (current_streak = 0 or wrong_streak = 0)
);

create index if not exists attempts_user_session_idx on attempts (user_id, session_id);
create index if not exists attempts_created_idx      on attempts (created_at);
create index if not exists attempts_labels_idx       on attempts (teaching_action, confidence_state);
create index if not exists attempts_synthetic_idx    on attempts (is_synthetic);

-- Idempotent replay guard: the web app retries queued rows after a network
-- drop, so the same attempt can be POSTed more than once.
create unique index if not exists attempts_dedupe_idx
  on attempts (session_id, attempt_index)
  where is_synthetic = false;


-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
-- Note on Supabase's newer API keys: a `sb_publishable_...` key maps to the
-- `anon` role exactly as the legacy anon JWT did, so the policies below apply
-- to it unchanged. A `sb_secret_...` key maps to `service_role` and BYPASSES
-- every policy here -- which is why it must never appear in web/config.js.
--
-- The web app runs with the public anon key, so anon must be able to INSERT.
-- These policies also let anon SELECT, which is what makes tools/export_dataset.py
-- work without a service key.
--
-- Tradeoff, stated plainly: anyone holding the anon key (it ships in the
-- client, it is not a secret) can read this table. That is acceptable here
-- because rows contain anonymous participant codes and timing numbers, no
-- names or contact details. Do NOT put real participant names in user_id.
--
-- To lock reads down instead: drop the select policy below and give
-- export_dataset.py the service_role key via SUPABASE_SERVICE_KEY.

alter table attempts enable row level security;

drop policy if exists attempts_anon_insert on attempts;
create policy attempts_anon_insert on attempts
  for insert to anon with check (true);

drop policy if exists attempts_anon_select on attempts;
create policy attempts_anon_select on attempts
  for select to anon using (true);

-- No update/delete policy on purpose: collected data is append-only.


-- ---------------------------------------------------------------------------
-- Monitoring views -- check these DURING collection, not after
-- ---------------------------------------------------------------------------

-- Are all 9 output classes getting enough examples? Starved classes are the
-- single most likely reason training disappoints. Watch this daily.
create or replace view class_balance as
select 'teaching_action' as head,
       teaching_action   as class_id,
       count(*)                              as total,
       count(*) filter (where not is_synthetic) as real_rows,
       count(*) filter (where is_synthetic)     as synthetic_rows
from attempts group by teaching_action
union all
select 'confidence_state', confidence_state,
       count(*),
       count(*) filter (where not is_synthetic),
       count(*) filter (where is_synthetic)
from attempts group by confidence_state
order by head, class_id;

-- Per-participant progress. session_days matters: features 8 and 10
-- (session_number, time_since_last_practice) are dead if everyone does all
-- their sessions in one sitting.
create or replace view participant_progress as
select user_id,
       count(*)                                     as attempts,
       count(distinct session_id)                   as sessions,
       count(distinct date(created_at))             as session_days,
       round(avg(case when is_correct then 1 else 0 end)::numeric, 3) as accuracy,
       count(distinct char_id)                      as chars_seen,
       min(created_at)                              as first_seen,
       max(created_at)                              as last_seen
from attempts
where not is_synthetic
group by user_id
order by attempts desc;

-- Which characters are hardest? Useful for the report, and for spotting a
-- wrong Braille mapping (a character nobody ever gets right is suspicious).
create or replace view character_difficulty as
select char_id,
       count(*)                                                        as attempts,
       round(avg(case when is_correct then 1 else 0 end)::numeric, 3)  as accuracy,
       round(avg(response_time)::numeric, 0)                           as avg_response_ms,
       round(avg(retry_count)::numeric, 2)                             as avg_retries
from attempts
where not is_synthetic
group by char_id
order by accuracy asc;

-- Overall collection dashboard.
create or replace view collection_summary as
select count(*)                                       as total_rows,
       count(*) filter (where not is_synthetic)       as real_rows,
       count(*) filter (where is_synthetic)           as synthetic_rows,
       count(distinct user_id) filter (where not is_synthetic)    as participants,
       count(distinct session_id) filter (where not is_synthetic) as sessions,
       count(distinct date(created_at)) filter (where not is_synthetic) as collection_days,
       bool_and(braille_map_verified)                 as all_rows_verified_map
from attempts;
