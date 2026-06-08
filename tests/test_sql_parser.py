from contextgraph_studio.parsers.sql_parser import PARSER_VERSION, SqlParser


def test_sql_parser_extracts_tables_views_and_indexes() -> None:
    content = (
        "CREATE TABLE IF NOT EXISTS public.users (\n"
        "  id INTEGER PRIMARY KEY\n"
        ");\n\n"
        'CREATE VIEW "active_users" AS SELECT * FROM public.users;\n'
        'CREATE UNIQUE INDEX [idx_users_email] ON public.users(email);\n'
    )
    result = SqlParser().parse("schema.sql", content, "file-1")
    entities = {(entity.entity_type, entity.symbol_name) for entity in result.entities}

    assert result.parse_errors == []
    assert result.parser_version == PARSER_VERSION
    assert ("db_table", "public.users") in entities
    assert ("db_view", "active_users") in entities
    assert ("db_index", "idx_users_email") in entities
    assert all(entity.line_start is not None and entity.line_end is not None for entity in result.entities)


def test_sql_parser_handles_multiple_statements_and_soft_failure() -> None:
    content = (
        'CREATE TABLE "user_accounts" (\n'
        "  id INTEGER PRIMARY KEY\n"
        ");\n"
        "CREATE TABLE broken (\n"
        "CREATE INDEX idx_user_accounts_username ON \"user_accounts\"(username);\n"
    )
    result = SqlParser().parse("migration.sql", content, "file-1")
    entities = {(entity.entity_type, entity.symbol_name) for entity in result.entities}
    assert ("db_table", "user_accounts") in entities
    assert ("db_index", "idx_user_accounts_username") in entities
    assert result.parse_errors
