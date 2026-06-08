"""Minimal Tree-sitter parser for TypeScript, TSX, JavaScript, and JSX."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from functools import lru_cache
from pathlib import PurePosixPath

from tree_sitter import Language, Node, Parser
import tree_sitter_javascript
import tree_sitter_typescript

from contextgraph_studio.domain import EntityRecord, ParseResult, RelationRecord


TREE_SITTER_VERSION = importlib.metadata.version("tree-sitter")
TREE_SITTER_JS_VERSION = importlib.metadata.version("tree-sitter-javascript")
TREE_SITTER_TS_VERSION = importlib.metadata.version("tree-sitter-typescript")
PARSER_VERSION = (
    "tree-sitter-js-ts-v1"
    f"+core-{TREE_SITTER_VERSION}"
    f"+js-{TREE_SITTER_JS_VERSION}"
    f"+ts-{TREE_SITTER_TS_VERSION}"
)
ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "use"}


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _line_start(node: Node) -> int:
    return node.start_point.row + 1


def _line_end(node: Node) -> int:
    return node.end_point.row + 1


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _relation_meta(**kwargs: object) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


def _module_symbol_for_path(file_path: str) -> str:
    pure = PurePosixPath(file_path)
    if pure.suffix:
        pure = pure.with_suffix("")
    return pure.as_posix()


def _normalize_relative_module(file_path: str, specifier: str) -> str | None:
    if not specifier.startswith("."):
        return None
    current_dir = PurePosixPath(file_path).parent
    candidate = current_dir.joinpath(specifier)
    parts: list[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    normalized = PurePosixPath(*parts)
    if normalized.suffix:
        normalized = normalized.with_suffix("")
    return normalized.as_posix()


def _named_children(node: Node) -> list[Node]:
    return [child for child in node.children if child.is_named]


def _unwrap_export(node: Node) -> tuple[Node, bool]:
    if node.type == "export_statement":
        named = _named_children(node)
        if named:
            return named[0], True
    return node, False


def _call_target_name(node: Node, source: bytes) -> str | None:
    if node.type == "identifier":
        return _node_text(node, source)
    if node.type == "property_identifier":
        return _node_text(node, source)
    if node.type == "member_expression":
        prop = node.child_by_field_name("property")
        if prop is not None:
            return _call_target_name(prop, source)
    return None


@lru_cache(maxsize=4)
def _language_for(language: str) -> Language:
    if language == "typescript":
        return Language(tree_sitter_typescript.language_typescript())
    if language == "tsx":
        return Language(tree_sitter_typescript.language_tsx())
    if language in {"javascript", "jsx"}:
        return Language(tree_sitter_javascript.language())
    raise ValueError(f"Unsupported TypeScript parser language: {language}")


@lru_cache(maxsize=4)
def _parser_for(language: str) -> Parser:
    parser = Parser()
    parser.language = _language_for(language)
    return parser


class TypeScriptParser:
    """Minimal parser loop for JS/TS-family source files."""

    def parse(
        self,
        file_path: str,
        content: str,
        file_id: str,
        language: str,
    ) -> ParseResult:
        del file_id
        module_symbol = _module_symbol_for_path(file_path)
        source = content.encode("utf-8")
        parse_errors: list[str] = []
        relations: list[RelationRecord] = []
        entities: list[EntityRecord] = [
            EntityRecord(
                entity_type="module",
                symbol_name=module_symbol,
                display_name=PurePosixPath(file_path).name,
                line_start=1,
                line_end=max(1, len(content.splitlines())),
                signature=None,
                docstring=None,
                language=language,
                content_hash=_hash_text(content),
                parent_symbol_name=None,
            )
        ]

        tree = _parser_for(language).parse(source)
        root = tree.root_node
        if root.has_error:
            parse_errors.append(f"{file_path}: tree-sitter parse error")
            return ParseResult(
                entities=entities,
                relations=relations,
                parse_errors=parse_errors,
                language=language,
                parser_version=PARSER_VERSION,
            )

        top_level_symbols: dict[str, str] = {}
        import_aliases: dict[str, str] = {}
        class_method_names: dict[str, set[str]] = {}

        for child in _named_children(root):
            statement, _ = _unwrap_export(child)
            if statement.type == "function_declaration":
                name_node = statement.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, source)
                    top_level_symbols[name] = f"{module_symbol}.{name}"
            elif statement.type == "class_declaration":
                name_node = statement.child_by_field_name("name")
                if name_node is not None:
                    class_name = _node_text(name_node, source)
                    top_level_symbols[class_name] = f"{module_symbol}.{class_name}"
                    body = statement.child_by_field_name("body")
                    if body is not None:
                        class_method_names[class_name] = {
                            _node_text(name_node, source)
                            for name_node in (
                                method.child_by_field_name("name")
                                for method in _named_children(body)
                                if method.type == "method_definition"
                            )
                            if name_node is not None
                        }
            elif statement.type in {"lexical_declaration", "variable_declaration"}:
                for declarator in _named_children(statement):
                    if declarator.type != "variable_declarator":
                        continue
                    name_node = declarator.child_by_field_name("name")
                    value_node = declarator.child_by_field_name("value")
                    if name_node is None or value_node is None:
                        continue
                    if name_node.type == "identifier" and value_node.type in {"arrow_function", "function_expression"}:
                        name = _node_text(name_node, source)
                        top_level_symbols[name] = f"{module_symbol}.{name}"

        for child in _named_children(root):
            statement, exported = _unwrap_export(child)
            if statement.type == "import_statement":
                self._collect_imports(
                    statement,
                    source,
                    file_path,
                    module_symbol,
                    relations,
                    import_aliases,
                )
                continue
            if statement.type in {"lexical_declaration", "variable_declaration"}:
                self._collect_require_aliases(statement, source, file_path, module_symbol, relations, import_aliases)

        for child in _named_children(root):
            statement, exported = _unwrap_export(child)
            if statement.type == "function_declaration":
                entity = self._build_function_entity(statement, source, module_symbol, language, exported)
                entities.append(entity)
                relations.extend(
                    self._collect_calls(
                        body_owner=statement,
                        owner_symbol=entity.symbol_name or entity.display_name,
                        source=source,
                        module_symbol=module_symbol,
                        top_level_symbols=top_level_symbols,
                        import_aliases=import_aliases,
                    )
                )
            elif statement.type in {"lexical_declaration", "variable_declaration"}:
                function_entities = self._build_variable_function_entities(
                    statement,
                    source,
                    module_symbol,
                    language,
                    exported,
                )
                entities.extend(entity for entity, _ in function_entities)
                for entity, body_node in function_entities:
                    relations.extend(
                        self._collect_calls(
                            body_owner=body_node,
                            owner_symbol=entity.symbol_name or entity.display_name,
                            source=source,
                            module_symbol=module_symbol,
                            top_level_symbols=top_level_symbols,
                            import_aliases=import_aliases,
                        )
                    )
            elif statement.type == "class_declaration":
                class_entity, method_pairs = self._build_class_entities(
                    statement,
                    source,
                    module_symbol,
                    language,
                    exported,
                )
                entities.append(class_entity)
                entities.extend(entity for entity, _ in method_pairs)
                method_names = class_method_names.get(class_entity.display_name, set())
                for entity, body_node in method_pairs:
                    relations.extend(
                        self._collect_calls(
                            body_owner=body_node,
                            owner_symbol=entity.symbol_name or entity.display_name,
                            source=source,
                            module_symbol=module_symbol,
                            top_level_symbols=top_level_symbols,
                            import_aliases=import_aliases,
                            class_symbol=class_entity.symbol_name,
                            class_method_names=method_names,
                        )
                    )

            route_entity, route_relation = self._build_api_route_entity(
                statement,
                source,
                module_symbol,
                language,
                top_level_symbols,
                import_aliases,
                class_method_names,
            )
            if route_entity is not None:
                entities.append(route_entity)
            if route_relation is not None:
                relations.append(route_relation)

        return ParseResult(
            entities=entities,
            relations=relations,
            parse_errors=parse_errors,
            language=language,
            parser_version=PARSER_VERSION,
        )

    def _collect_imports(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        module_symbol: str,
        relations: list[RelationRecord],
        import_aliases: dict[str, str],
    ) -> None:
        source_node = node.child_by_field_name("source")
        if source_node is None:
            return
        specifier = _node_text(source_node, source).strip("\"'")
        resolved_module = _normalize_relative_module(file_path, specifier)
        if resolved_module is None:
            return

        clause = next((child for child in _named_children(node) if child.type == "import_clause"), None)
        if clause is None:
            relations.append(RelationRecord("imports", module_symbol, resolved_module))
            return

        for child in _named_children(clause):
            if child.type == "identifier":
                local_name = _node_text(child, source)
                import_aliases[local_name] = f"{resolved_module}.{local_name}"
                relations.append(RelationRecord("imports", module_symbol, import_aliases[local_name]))
            elif child.type == "named_imports":
                for spec in _named_children(child):
                    if spec.type == "import_specifier":
                        identifiers = [named for named in _named_children(spec) if named.type == "identifier"]
                        imported_name = _node_text(identifiers[0], source) if identifiers else None
                        if not imported_name:
                            continue
                        local_name = _node_text(identifiers[-1], source) if len(identifiers) > 1 else imported_name
                        target_symbol = f"{resolved_module}.{imported_name}"
                        import_aliases[local_name] = target_symbol
                        relations.append(RelationRecord("imports", module_symbol, target_symbol))
            elif child.type == "namespace_import":
                name_node = next((named for named in _named_children(child) if named.type == "identifier"), None)
                if name_node is not None:
                    local_name = _node_text(name_node, source)
                    import_aliases[local_name] = resolved_module
                    relations.append(RelationRecord("imports", module_symbol, resolved_module))

    def _collect_require_aliases(
        self,
        node: Node,
        source: bytes,
        file_path: str,
        module_symbol: str,
        relations: list[RelationRecord],
        import_aliases: dict[str, str],
    ) -> None:
        for declarator in _named_children(node):
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None or value_node.type != "call_expression":
                continue
            func = value_node.child_by_field_name("function")
            args = value_node.child_by_field_name("arguments")
            if func is None or args is None or _node_text(func, source) != "require":
                continue
            arg_nodes = [child for child in _named_children(args) if child.type == "string"]
            if not arg_nodes:
                continue
            specifier = _node_text(arg_nodes[0], source).strip("\"'")
            resolved_module = _normalize_relative_module(file_path, specifier)
            if resolved_module is None:
                continue
            if name_node.type == "identifier":
                import_aliases[_node_text(name_node, source)] = resolved_module
            relations.append(RelationRecord("imports", module_symbol, resolved_module))

    def _build_function_entity(
        self,
        node: Node,
        source: bytes,
        module_symbol: str,
        language: str,
        exported: bool,
    ) -> EntityRecord:
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, source) if name_node is not None else "anonymous"
        signature = _node_text(node, source)
        if exported and not signature.startswith("export "):
            signature = f"export {signature}"
        snippet = _node_text(node, source)
        return EntityRecord(
            entity_type="function",
            symbol_name=f"{module_symbol}.{name}",
            display_name=name,
            line_start=_line_start(node),
            line_end=_line_end(node),
            signature=signature,
            docstring=None,
            language=language,
            content_hash=_hash_text(snippet),
            parent_symbol_name=module_symbol,
        )

    def _build_variable_function_entities(
        self,
        node: Node,
        source: bytes,
        module_symbol: str,
        language: str,
        exported: bool,
    ) -> list[tuple[EntityRecord, Node]]:
        results: list[tuple[EntityRecord, Node]] = []
        for declarator in _named_children(node):
            if declarator.type != "variable_declarator":
                continue
            name_node = declarator.child_by_field_name("name")
            value_node = declarator.child_by_field_name("value")
            if name_node is None or value_node is None or name_node.type != "identifier":
                continue
            if value_node.type not in {"arrow_function", "function_expression"}:
                continue
            name = _node_text(name_node, source)
            declaration_text = _node_text(declarator, source)
            signature = declaration_text
            if exported and not signature.startswith("export "):
                signature = f"export {signature}"
            results.append(
                (
                    EntityRecord(
                        entity_type="function",
                        symbol_name=f"{module_symbol}.{name}",
                        display_name=name,
                        line_start=_line_start(declarator),
                        line_end=_line_end(declarator),
                        signature=signature,
                        docstring=None,
                        language=language,
                        content_hash=_hash_text(declaration_text),
                        parent_symbol_name=module_symbol,
                    ),
                    value_node,
                )
            )
        return results

    def _build_class_entities(
        self,
        node: Node,
        source: bytes,
        module_symbol: str,
        language: str,
        exported: bool,
    ) -> tuple[EntityRecord, list[tuple[EntityRecord, Node]]]:
        name_node = node.child_by_field_name("name")
        class_name = _node_text(name_node, source) if name_node is not None else "AnonymousClass"
        class_symbol = f"{module_symbol}.{class_name}"
        signature = _node_text(node, source)
        if exported and not signature.startswith("export "):
            signature = f"export {signature}"
        class_entity = EntityRecord(
            entity_type="class",
            symbol_name=class_symbol,
            display_name=class_name,
            line_start=_line_start(node),
            line_end=_line_end(node),
            signature=signature,
            docstring=None,
            language=language,
            content_hash=_hash_text(_node_text(node, source)),
            parent_symbol_name=module_symbol,
        )
        method_entities: list[tuple[EntityRecord, Node]] = []
        body = node.child_by_field_name("body")
        if body is None:
            return class_entity, method_entities
        for method in _named_children(body):
            if method.type != "method_definition":
                continue
            method_name_node = method.child_by_field_name("name")
            if method_name_node is None:
                continue
            method_name = _node_text(method_name_node, source)
            method_entities.append(
                (
                    EntityRecord(
                        entity_type="method",
                        symbol_name=f"{class_symbol}.{method_name}",
                        display_name=method_name,
                        line_start=_line_start(method),
                        line_end=_line_end(method),
                        signature=_node_text(method, source),
                        docstring=None,
                        language=language,
                        content_hash=_hash_text(_node_text(method, source)),
                        parent_symbol_name=class_symbol,
                    ),
                    method,
                )
            )
        return class_entity, method_entities

    def _collect_calls(
        self,
        *,
        body_owner: Node,
        owner_symbol: str,
        source: bytes,
        module_symbol: str,
        top_level_symbols: dict[str, str],
        import_aliases: dict[str, str],
        class_symbol: str | None = None,
        class_method_names: set[str] | None = None,
    ) -> list[RelationRecord]:
        call_counts: dict[str, tuple[str, int]] = {}
        stack = [body_owner]
        while stack:
            node = stack.pop()
            if node.type == "call_expression":
                func = node.child_by_field_name("function")
                if func is not None:
                    target_symbol, call_name = self._resolve_call_target(
                        func,
                        source,
                        module_symbol,
                        top_level_symbols,
                        import_aliases,
                        class_symbol,
                        class_method_names,
                    )
                    if target_symbol and call_name:
                        _, count = call_counts.get(target_symbol, (call_name, 0))
                        call_counts[target_symbol] = (call_name, count + 1)
            stack.extend(reversed(_named_children(node)))
        return [
            RelationRecord(
                edge_type="calls",
                from_symbol_name=owner_symbol,
                to_symbol_name=target_symbol,
                meta_json=_relation_meta(call_name=call_name, call_count=count),
            )
            for target_symbol, (call_name, count) in call_counts.items()
        ]

    def _resolve_call_target(
        self,
        node: Node,
        source: bytes,
        module_symbol: str,
        top_level_symbols: dict[str, str],
        import_aliases: dict[str, str],
        class_symbol: str | None,
        class_method_names: set[str] | None,
    ) -> tuple[str | None, str | None]:
        if node.type == "identifier":
            name = _node_text(node, source)
            if name in top_level_symbols:
                return top_level_symbols[name], name
            if name in import_aliases:
                return import_aliases[name], name
            return name, name
        if node.type == "member_expression":
            object_node = node.child_by_field_name("object")
            property_node = node.child_by_field_name("property")
            call_name = _call_target_name(property_node, source) if property_node is not None else None
            if object_node is not None and property_node is not None:
                object_name = _call_target_name(object_node, source)
                if object_name == "this" and class_symbol and class_method_names and call_name in class_method_names:
                    return f"{class_symbol}.{call_name}", call_name
                if object_name in import_aliases and call_name:
                    return f"{import_aliases[object_name]}.{call_name}", call_name
            return call_name, call_name
        return None, None

    def _build_api_route_entity(
        self,
        node: Node,
        source: bytes,
        module_symbol: str,
        language: str,
        top_level_symbols: dict[str, str],
        import_aliases: dict[str, str],
        class_method_names: dict[str, set[str]],
    ) -> tuple[EntityRecord | None, RelationRecord | None]:
        call_node = node
        if node.type == "expression_statement":
            call_node = node.children[0]
        if call_node.type != "call_expression":
            return None, None
        function_node = call_node.child_by_field_name("function")
        arguments_node = call_node.child_by_field_name("arguments")
        if function_node is None or arguments_node is None or function_node.type != "member_expression":
            return None, None
        object_node = function_node.child_by_field_name("object")
        property_node = function_node.child_by_field_name("property")
        if object_node is None or property_node is None:
            return None, None
        method = _node_text(property_node, source).lower()
        if method not in ROUTE_METHODS:
            return None, None
        arg_nodes = [child for child in _named_children(arguments_node)]
        if len(arg_nodes) < 2 or arg_nodes[0].type != "string":
            return None, None
        route_path = _node_text(arg_nodes[0], source).strip("\"'")
        handler_node = arg_nodes[1]
        handler_symbol, handler_name = self._resolve_call_target(
            handler_node,
            source,
            module_symbol,
            top_level_symbols,
            import_aliases,
            class_symbol=None,
            class_method_names=None,
        )
        route_display = f"{method.upper()} {route_path}"
        route_symbol = f"{module_symbol}::{route_display}"
        signature = route_display if not handler_name else f"{route_display} -> {handler_name}"
        entity = EntityRecord(
            entity_type="api_route",
            symbol_name=route_symbol,
            display_name=route_display,
            line_start=_line_start(call_node),
            line_end=_line_end(call_node),
            signature=signature,
            docstring=None,
            language=language,
            content_hash=_hash_text(_node_text(call_node, source)),
            parent_symbol_name=module_symbol,
        )
        relation = None
        if handler_symbol is not None:
            relation = RelationRecord(
                edge_type="route_to_handler",
                from_symbol_name=route_symbol,
                to_symbol_name=handler_symbol,
                meta_json=_relation_meta(
                    method=method.upper(),
                    path=route_path,
                    router=_node_text(object_node, source),
                ),
            )
        return entity, relation
