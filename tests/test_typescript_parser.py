from pathlib import Path

from contextgraph_studio.parsers.typescript_parser import PARSER_VERSION, TypeScriptParser


def test_typescript_parser_extracts_functions_classes_methods_and_routes() -> None:
    content = (
        'import { loginHandler } from "./auth"\n'
        "export async function loadData(token: string) {\n"
        "  return parseConfig(token)\n"
        "}\n"
        "const parseConfig = () => tokenCache()\n"
        "const legacy = function () { return parseConfig() }\n"
        "class AuthService {\n"
        "  verifyToken(token: string) {\n"
        "    this.validate()\n"
        "    return token\n"
        "  }\n"
        "  validate() { return true }\n"
        "}\n"
        'router.post("/login", loginHandler)\n'
    )

    result = TypeScriptParser().parse("src/routes.ts", content, "file-1", "typescript")
    symbols = {entity.symbol_name for entity in result.entities}

    assert result.parse_errors == []
    assert result.parser_version == PARSER_VERSION
    assert "src/routes.loadData" in symbols
    assert "src/routes.parseConfig" in symbols
    assert "src/routes.legacy" in symbols
    assert "src/routes.AuthService" in symbols
    assert "src/routes.AuthService.verifyToken" in symbols
    assert "src/routes::POST /login" in symbols
    assert any(relation.edge_type == "imports" and relation.to_symbol_name == "src/auth.loginHandler" for relation in result.relations)
    assert any(relation.edge_type == "calls" and relation.to_symbol_name == "src/routes.parseConfig" for relation in result.relations)
    assert any(
        relation.edge_type == "route_to_handler" and relation.to_symbol_name == "src/auth.loginHandler"
        for relation in result.relations
    )


def test_tsx_js_and_jsx_are_supported() -> None:
    parser = TypeScriptParser()

    tsx = parser.parse("src/components/Login.tsx", "export const Login = () => <div>Login</div>\n", "file-1", "tsx")
    assert any(entity.symbol_name == "src/components/Login.Login" for entity in tsx.entities)

    js = parser.parse(
        "src/utils.js",
        'const path = require("path")\nconst helper = function () { return true }\nfunction run() { return helper() }\n',
        "file-2",
        "javascript",
    )
    assert any(entity.symbol_name == "src/utils.helper" for entity in js.entities)
    assert any(entity.symbol_name == "src/utils.run" for entity in js.entities)
    assert any(relation.edge_type == "calls" and relation.to_symbol_name == "src/utils.helper" for relation in js.relations)

    jsx = parser.parse("src/App.jsx", "const App = () => <section>Hi</section>\n", "file-3", "jsx")
    assert any(entity.symbol_name == "src/App.App" for entity in jsx.entities)


def test_typescript_syntax_error_is_soft() -> None:
    result = TypeScriptParser().parse("src/broken.ts", "export function broken( {\n  return true\n}\n", "file-1", "typescript")
    assert result.parse_errors
    assert result.entities[0].entity_type == "module"
    assert len(result.entities) == 1
