"""Python AST 解析器。"""

import ast
import hashlib
import json

from contextgraph_studio.domain import EntityRecord, ParseResult, RelationRecord


PARSER_VERSION = "python-ast-v1"


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _signature_for_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({ast.unparse(node.args)})"


def _signature_for_class(node: ast.ClassDef) -> str:
    if node.bases:
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        return f"class {node.name}({bases})"
    return f"class {node.name}"


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return None


def _relation_meta(**kwargs: object) -> str:
    return json.dumps(kwargs, ensure_ascii=False)


def _collect_calls(
    body_owner: ast.FunctionDef | ast.AsyncFunctionDef,
    owner_symbol: str,
    module_symbol: str,
    known_local_symbols: set[str],
    class_symbol: str | None = None,
    class_method_names: set[str] | None = None,
) -> list[RelationRecord]:
    call_counts: dict[str, tuple[str, int]] = {}
    for node in ast.walk(body_owner):
        if not isinstance(node, ast.Call):
            continue
        target_name: str | None = None
        call_name: str | None = None
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
            if call_name in known_local_symbols:
                target_name = f"{module_symbol}.{call_name}"
            else:
                target_name = call_name
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and class_symbol
                and class_method_names
                and call_name in class_method_names
            ):
                target_name = f"{class_symbol}.{call_name}"
            else:
                target_name = call_name

        if not target_name or not call_name:
            continue
        previous_target, count = call_counts.get(target_name, (call_name, 0))
        call_counts[target_name] = (previous_target, count + 1)

    return [
        RelationRecord(
            edge_type="calls",
            from_symbol_name=owner_symbol,
            to_symbol_name=target_name,
            meta_json=_relation_meta(call_name=call_name, call_count=count),
        )
        for target_name, (call_name, count) in call_counts.items()
    ]


class PythonParser:
    """最小 Python AST parser。"""

    def parse(self, file_path: str, content: str, file_id: str) -> ParseResult:
        parse_errors: list[str] = []
        entities: list[EntityRecord] = []
        relations: list[RelationRecord] = []
        file_stem = file_path.removesuffix(".py").replace("/", ".")
        module_symbol = file_stem or file_path

        module_record = EntityRecord(
            entity_type="module",
            symbol_name=module_symbol,
            display_name=file_path.split("/")[-1],
            line_start=1,
            line_end=max(1, len(content.splitlines())),
            signature=None,
            docstring=None,
            language="python",
            content_hash=_hash_text(content),
            parent_symbol_name=None,
        )
        entities.append(module_record)

        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as exc:
            parse_errors.append(f"{file_path}:{exc.lineno}:{exc.offset}: {exc.msg}")
            return ParseResult(
                entities=entities,
                relations=relations,
                parse_errors=parse_errors,
                language="python",
                parser_version=PARSER_VERSION,
            )

        module_doc = ast.get_docstring(tree)
        entities[0].docstring = module_doc
        top_level_symbols: set[str] = set()
        class_method_lookup: dict[str, set[str]] = {}

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_level_symbols.add(node.name)
            if isinstance(node, ast.ClassDef):
                class_method_lookup[node.name] = {
                    child.name
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                }

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    relations.append(
                        RelationRecord(
                            edge_type="imports",
                            from_symbol_name=module_symbol,
                            to_symbol_name=alias.name,
                            meta_json=None,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names:
                    imported = f"{module_name}.{alias.name}".strip(".")
                    relations.append(
                        RelationRecord(
                            edge_type="imports",
                            from_symbol_name=module_symbol,
                            to_symbol_name=imported,
                            meta_json=None,
                        )
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_symbol = f"{module_symbol}.{node.name}"
                snippet = ast.get_source_segment(content, node) or node.name
                entities.append(
                    EntityRecord(
                        entity_type="function",
                        symbol_name=function_symbol,
                        display_name=node.name,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=_signature_for_function(node),
                        docstring=ast.get_docstring(node),
                        language="python",
                        content_hash=_hash_text(snippet),
                        parent_symbol_name=module_symbol,
                    )
                )
                relations.extend(
                    _collect_calls(
                        node,
                        function_symbol,
                        module_symbol,
                        known_local_symbols=top_level_symbols,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                class_symbol = f"{module_symbol}.{node.name}"
                class_snippet = ast.get_source_segment(content, node) or node.name
                entities.append(
                    EntityRecord(
                        entity_type="class",
                        symbol_name=class_symbol,
                        display_name=node.name,
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=_signature_for_class(node),
                        docstring=ast.get_docstring(node),
                        language="python",
                        content_hash=_hash_text(class_snippet),
                        parent_symbol_name=module_symbol,
                    )
                )
                for base in node.bases:
                    base_name = _dotted_name(base)
                    if not base_name:
                        continue
                    if base_name in top_level_symbols:
                        target_name = f"{module_symbol}.{base_name}"
                    else:
                        target_name = base_name
                    relations.append(
                        RelationRecord(
                            edge_type="inherits",
                            from_symbol_name=class_symbol,
                            to_symbol_name=target_name,
                            weight=1.5,
                            meta_json=_relation_meta(base_name=base_name),
                        )
                    )
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_symbol = f"{class_symbol}.{child.name}"
                        child_snippet = ast.get_source_segment(content, child) or child.name
                        entities.append(
                            EntityRecord(
                                entity_type="method",
                                symbol_name=method_symbol,
                                display_name=child.name,
                                line_start=child.lineno,
                                line_end=getattr(child, "end_lineno", child.lineno),
                                signature=_signature_for_function(child),
                                docstring=ast.get_docstring(child),
                                language="python",
                                content_hash=_hash_text(child_snippet),
                                parent_symbol_name=class_symbol,
                            )
                        )
                        relations.extend(
                            _collect_calls(
                                child,
                                method_symbol,
                                module_symbol,
                                known_local_symbols=top_level_symbols,
                                class_symbol=class_symbol,
                                class_method_names=class_method_lookup.get(node.name, set()),
                            )
                        )

        return ParseResult(
            entities=entities,
            relations=relations,
            parse_errors=parse_errors,
            language="python",
            parser_version=PARSER_VERSION,
        )
