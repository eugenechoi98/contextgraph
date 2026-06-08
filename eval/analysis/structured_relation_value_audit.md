# Structured Relation Value Audit

Date: 2026-06-08

Phase: 4D.2

## Scope

This audit checks whether structured SQL/config nodes need immediate cross-file graph edges.

Current completed baseline:

- SQL/config structured parsers
- `schema` / `config` BM25 candidate lanes
- `database` / `configuration` task strategies
- structured fixture eval dataset

This round did not implement a new edge.

## Fixture Expansion

Added source consumers to `tests/fixtures/sample_structured_repo`:

- `src/user_repository.py`
- `src/config_loader.py`
- `src/server.py`

The first two contain clear static consumers. `src/server.py` is a negative example with natural language strings.

## Database Audit

SQL structured entities:

- `public.users`
- `active_users`
- `idx_users_email`
- `user_accounts`
- `idx_user_accounts_username`

Detected `uses_table` candidates:

- candidate count: `4`
- safe to materialize: `3`
- skipped: `1`

High-confidence candidates:

- `src.user_repository -> public.users`
  - match type: `table_name_constant`
  - matched text: `users`
- `src.user_repository.find_user_by_email -> public.users`
  - match type: `sql_string_table_name`
  - matched text: `FROM users`
- `src.user_repository.update_account_status -> public.users`
  - match type: `sql_string_table_name`
  - matched text: `UPDATE users`

Skipped candidate:

- `src/server.py -> public.users`
  - match type: `natural_language_string`
  - matched text: `users can update their profile`
  - reason: `not_sql_or_table_constant`

Verdict:

- `uses_table` is statically detectable for this fixture.
- However, current retrieval already returns both schema files and consumer source for the structured database queries.
- The required implementation gate is not met because there are not at least two real fixture queries where the structured file is hit but consumer source is missing.

## Configuration Audit

Config structured entities include:

- `database.host`
- `database.port`
- `database.password`
- `api.timeout`
- `service.token`
- `auth.api_key`

Detected `configures` candidates:

- candidate count: `11`
- safe to materialize: `4`
- skipped: `7`

High-confidence candidates:

- `src.config_loader -> database.host`
  - match type: `config_key_access`
  - matched text: `database.host`
- `src.config_loader.get_api_timeout -> api.timeout`
  - match type: `config_key_access`
  - matched text: `api.timeout`
- `src.config_loader -> database`
  - match type: `config_key_access`
  - matched text: `database`
- `src.config_loader.get_api_timeout -> api`
  - match type: `config_key_access`
  - matched text: `api`

Skipped candidates include natural-language or broad term matches in `src/config_loader.py` and `src/server.py`.

Verdict:

- `configures` can be recorded as diagnostics.
- It is riskier to materialize now because config key access can be dynamic, wrapped, or duplicated across equivalent config files.
- Current retrieval already returns both config files and consumer source for the structured configuration queries.

## Retrieval Gap Check

Structured eval dataset:

- `eval/fixtures/structured_golden.json`

Eval smoke:

- `bm25_only`
  - MRR: `0.6458`
  - Recall@5: `1.0`
  - critical_file_hit_rate: `1.0`
- `bm25_graph`
  - MRR: `0.6458`
  - Recall@5: `1.0`
  - critical_file_hit_rate: `1.0`

Per-case retrieval:

- `database_table_001`
  - structured file hit: yes
  - consumer source hit: yes, `src/user_repository.py`
  - graph hit count: `0`
- `database_index_001`
  - structured file hit: yes
  - consumer source hit: yes, `src/user_repository.py`
  - graph hit count: `0`
- `configuration_host_001`
  - structured file hit: yes
  - consumer source hit: yes, `src/config_loader.py`
  - graph hit count: `0`
- `configuration_json_001`
  - structured file hit: yes
  - consumer source hit: yes, `src/config_loader.py`
  - graph hit count: `0`

Graph diagnostics:

- Graph did not contribute to these structured fixture cases.
- `bm25_graph` matched `bm25_only` metrics, so there is no measured Graph lift in this fixture.
- The common graph reason is `edge_type_filtered`, which is expected because no structured cross-file edge is currently allowed.

## Decision

Do not implement `uses_table` or `configures` in Phase 4D.2.

Reason:

- The diagnostic rules can identify high-confidence candidates.
- Negative examples are also present and correctly skipped.
- But the current retrieval stack already returns both structured files and consumer source for the tested structured queries.
- There is no current bad case proving that a new edge is needed.

## Next Step

Keep structured relation diagnostics as evidence.

Only implement `uses_table` later if a real retrieval gap appears where:

- SQL schema is hit
- consumer source is missed
- the relation is recoverable with simple static SQL/table-name rules
- negative examples remain safe
