from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

CRITICAL_IMPORTS = {
    "ctypes": "Direct native-library access",
}

HIGH_IMPORTS = {
    "subprocess": "Process spawning",
    "socket": "Raw network access",
    "requests": "Network access",
    "urllib": "Network access",
    "http": "Network access",
}

HIGH_CALLS = {
    "eval": "Dynamic code execution",
    "exec": "Dynamic code execution",
    "compile": "Dynamic code execution",
    "__import__": "Dynamic importing",
    "os.system": "Shell execution",
    "os.popen": "Shell execution",
    "subprocess.run": "Process spawning",
    "subprocess.Popen": "Process spawning",
    "subprocess.call": "Process spawning",
    "subprocess.check_call": "Process spawning",
    "subprocess.check_output": "Process spawning",
    "socket.socket": "Raw network socket creation",
    "shutil.rmtree": "Recursive filesystem deletion",
}

MEDIUM_CALLS = {
    "Path.unlink": "Filesystem mutation",
    "Path.rmdir": "Filesystem mutation",
    "Path.write_text": "Filesystem mutation",
    "Path.write_bytes": "Filesystem mutation",
    "os.remove": "Filesystem mutation",
    "os.unlink": "Filesystem mutation",
    "os.rmdir": "Filesystem mutation",
    "os.makedirs": "Filesystem mutation",
    "importlib.import_module": "Dynamic importing",
}

HIGH_STRING_MARKERS = {
    "sudo": "Direct elevation attempt",
    "pkexec": "Direct elevation attempt",
    "runas": "Direct elevation attempt",
    "authorizationexecutewithprivileges": "Direct elevation attempt",
    "shell.executew": "Direct elevation attempt",
    "shell.executewith": "Direct elevation attempt",
}


@dataclass(frozen=True)
class SecurityIssue:
    severity: str
    file_path: str
    line: int
    symbol: str
    message: str


@dataclass(frozen=True)
class SecurityReport:
    risk_level: str
    summary: str
    issues: list[SecurityIssue]

    def as_dict(self) -> dict[str, object]:
        return {
            "risk_level": self.risk_level,
            "summary": self.summary,
            "issues": [
                {
                    "severity": issue.severity,
                    "file_path": issue.file_path,
                    "line": issue.line,
                    "symbol": issue.symbol,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }


class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.issues: list[SecurityIssue] = []
        self._aliases: dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            self._aliases[alias.asname or root] = alias.name
            if root in CRITICAL_IMPORTS:
                self._add_issue("critical", node.lineno, alias.name, CRITICAL_IMPORTS[root])
            elif root in HIGH_IMPORTS:
                self._add_issue("high", node.lineno, alias.name, HIGH_IMPORTS[root])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = (node.module or "").strip()
        if module:
            root = module.split(".")[0]
            if root in CRITICAL_IMPORTS:
                self._add_issue("critical", node.lineno, module, CRITICAL_IMPORTS[root])
            elif root in HIGH_IMPORTS:
                self._add_issue("high", node.lineno, module, HIGH_IMPORTS[root])
            for alias in node.names:
                self._aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        symbol = self._resolve_symbol(node.func)
        if symbol in HIGH_CALLS:
            self._add_issue("high", node.lineno, symbol, HIGH_CALLS[symbol])
        elif symbol in MEDIUM_CALLS:
            self._add_issue("medium", node.lineno, symbol, MEDIUM_CALLS[symbol])
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            normalized = node.value.lower()
            for marker, reason in HIGH_STRING_MARKERS.items():
                if marker in normalized:
                    self._add_issue("high", node.lineno, marker, reason)
        self.generic_visit(node)

    def _resolve_symbol(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return self._aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = self._resolve_symbol(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    def _add_issue(self, severity: str, line: int, symbol: str, reason: str) -> None:
        self.issues.append(
            SecurityIssue(
                severity=severity,
                file_path=str(self.file_path),
                line=int(line),
                symbol=symbol,
                message=f"{reason} detected via '{symbol}'",
            )
        )



def scan_plugin_path(path: Path) -> SecurityReport:
    path = Path(path)
    files: list[Path] = []
    if path.is_file() and path.suffix == ".py":
        files = [path]
    elif path.is_dir():
        files = sorted(file_path for file_path in path.rglob("*.py") if "__pycache__" not in file_path.parts)

    issues: list[SecurityIssue] = []
    for file_path in files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except Exception as exc:
            issues.append(
                SecurityIssue(
                    severity="high",
                    file_path=str(file_path),
                    line=1,
                    symbol="parse_error",
                    message=f"Could not parse Python file: {exc}",
                )
            )
            continue
        visitor = _SecurityVisitor(file_path)
        visitor.visit(tree)
        issues.extend(visitor.issues)

    risk_level = "low"
    if issues:
        risk_level = max(issues, key=lambda issue: SEVERITY_ORDER[issue.severity]).severity

    if not issues:
        summary = "No risky imports or calls were detected by the static plugin scan."
    else:
        top_symbols: list[str] = []
        for issue in issues:
            if issue.symbol not in top_symbols:
                top_symbols.append(issue.symbol)
            if len(top_symbols) >= 4:
                break
        summary = f"Detected {len(issues)} potential risk marker(s): {', '.join(top_symbols)}."

    return SecurityReport(risk_level=risk_level, summary=summary, issues=issues)
