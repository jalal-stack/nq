#!/usr/bin/env python3
"""Static conflict audit of the imported MVP (legacy/mvp) against the canonical codebase.

Reads source code only (never imports or executes MVP code) and writes a Markdown report:
  - API route collisions and MVP-only routes to port
  - database schema findings (SQL migrations vs SQLAlchemy models vs canonical domain enums)
  - MVP modules that duplicate canonical Risk Engine / Paper Broker / strategy / data code
  - live-trading and secret-handling findings (blockers)
  - environment variable and dependency differences

Usage (from the repository root):
  python scripts/mvp_audit.py legacy/mvp --out docs/MVP_INTEGRATION_REPORT.md
Exit code 1 when blocking safety findings exist, otherwise 0.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANONICAL_API = REPO / "backend" / "trademind" / "api" / "main.py"
CANONICAL_ENV = REPO / ".env.example"
CANONICAL_PYPROJECT = REPO / "backend" / "pyproject.toml"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "websocket", "api_route"}

# MVP module (by file stem) -> canonical home. The MVP file is ported into the target, never imported.
CANONICAL_HOMES = {
    "risk": "backend/trademind/risk/engine.py (RiskEngine)",
    "paper": "backend/trademind/execution/paper.py (PaperBroker)",
    "strategy": "backend/trademind/backtest/engine.py (Strategy protocol, EmaRsiAtrStrategy)",
    "market_data": "backend/trademind/data/providers.py + data/validation.py",
    "config": "backend/trademind/config.py (Settings, paper-only validator)",
    "main": "backend/trademind/api/main.py (/api/v1 router)",
    "schemas": "backend/trademind/domain.py + risk/engine.py models (extend, do not fork)",
    "models": "backend/trademind/db/models.py (new; SQLAlchemy, adopts MVP tables)",
    "db": "backend/trademind/db/session.py (new)",
    "seed": "backend/trademind/db/seed.py (new)",
}
INDICATOR_FUNCS = {"ema", "sma", "rsi", "atr", "macd", "vwap", "bollinger", "adx", "true_range"}

# Live execution, signing or key material. Any hit blocks the merge until removed.
BLOCKER_PATTERNS = [
    (r"\bcreate_(market_|limit_)?(buy_|sell_)?order\s*\(", "exchange order submission"),
    (r"\b(place|submit|send)_order\s*\(", "order submission helper"),
    (r"\b(send|sign)_?[Tt]ransaction\b", "blockchain transaction signing/sending"),
    (r"\bprivate_?[Kk]ey\b|\bmnemonic\b|\bseed_phrase\b", "wallet key material"),
    (r"live_execution_enabled\s*[:=]\s*True", "live execution enabled"),
    (r"paper_only\s*[:=]\s*False", "paper-only disabled"),
    (r"['\"]apiKey['\"]\s*:", "authenticated exchange client"),
    (r"(sk-ant-|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[0-9A-Za-z]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY)",
     "hard-coded credential"),
]
WARN_PATTERNS = [
    (r"os\.(getenv|environ)\W+['\"][A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD)['\"]", "reads a credential from env"),
    (r"\bTRADING_MODE\b|\btrading_mode\b", "trading-mode switch (must stay paper-only)"),
]

MONEY_COL = re.compile(r"(price|qty|quantity|equity|balance|pnl|fee|amount|notional|cash|size|stop|target|"
                       r"take_profit|stop_loss|risk|value)", re.I)
TYPE_FAMILIES = {
    "float": {"float", "real", "double", "double precision", "float4", "float8"},
    "decimal": {"numeric", "decimal", "money"},
    "int": {"integer", "int", "bigint", "smallint", "serial", "bigserial", "biginteger", "smallinteger"},
    "str": {"text", "varchar", "string", "char", "character varying", "unicode", "unicodetext", "uuid"},
    "datetime": {"timestamp", "timestamptz", "timestamp with time zone", "timestamp without time zone",
                 "datetime", "date"},
    "bool": {"boolean", "bool"},
    "json": {"json", "jsonb"},
    "enum": {"enum"},
}


def family(t: str) -> str:
    t = re.sub(r"\(.*\)", "", t.lower()).strip()
    for fam, names in TYPE_FAMILIES.items():
        if t in names:
            return fam
    return t or "?"


@dataclass
class Route:
    method: str
    path: str
    where: str


@dataclass
class Column:
    name: str
    type: str
    where: str
    tz: bool | None = None
    enum_values: list[str] = field(default_factory=list)


@dataclass
class Finding:
    severity: str  # BLOCKER | CONFLICT | WARN | INFO
    area: str
    message: str


# ---------------------------------------------------------------- routes

def _const_str(node: ast.AST, consts: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                s = _const_str(v.value, consts)
                if s is None:
                    return None
                parts.append(s)
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _const_str(node.left, consts), _const_str(node.right, consts)
        return a + b if a is not None and b is not None else None
    return None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _expr_key(node: ast.AST) -> str:
    return ast.unparse(node)


def extract_routes(files: list[Path], root: Path) -> tuple[list[Route], list[str]]:
    """Best-effort FastAPI route extraction with APIRouter/include_router prefixes."""
    raw: list[tuple[str, str, str, str, str]] = []  # (file_stem, router_var, method, path, where)
    router_prefix: dict[tuple[str, str], str] = {}
    includes: list[tuple[str, str, str]] = []  # (target expr, prefix, where)
    notes: list[str] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            notes.append(f"`{f.relative_to(root)}`: syntax error, skipped ({e.msg})")
            continue
        consts = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                s = _const_str(node.value, consts)
                if s is not None:
                    consts[node.targets[0].id] = s
        stem = f.stem
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                fn = _expr_key(node.value.func).split(".")[-1]
                if fn in {"APIRouter", "FastAPI"} and isinstance(node.targets[0], ast.Name):
                    pfx = _kw(node.value, "prefix")
                    router_prefix[(stem, node.targets[0].id)] = (_const_str(pfx, consts) or "") if pfx else ""
            if isinstance(node, ast.Call) and _expr_key(node.func).endswith("include_router") and node.args:
                pfx = _kw(node, "prefix")
                includes.append((_expr_key(node.args[0]), (_const_str(pfx, consts) or "") if pfx else "",
                                 f"{f.relative_to(root)}:{node.lineno}"))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                        continue
                    method = dec.func.attr
                    if method not in HTTP_METHODS or not isinstance(dec.func.value, ast.Name):
                        continue
                    path = _const_str(dec.args[0], consts) if dec.args else _const_str(_kw(dec, "path") or ast.Constant(""), consts)
                    if path is None:
                        notes.append(f"`{f.relative_to(root)}:{dec.lineno}`: dynamic route path, check manually")
                        continue
                    if method == "api_route":
                        methods = _kw(dec, "methods")
                        names = [e.value for e in getattr(methods, "elts", []) if isinstance(e, ast.Constant)]
                        for m in names or ["GET"]:
                            raw.append((stem, dec.func.value.id, m.upper(), path, f"{f.relative_to(root)}:{dec.lineno}"))
                    else:
                        raw.append((stem, dec.func.value.id, "WS" if method == "websocket" else method.upper(),
                                    path, f"{f.relative_to(root)}:{dec.lineno}"))

    routes = []
    for stem, var, method, path, where in raw:
        prefix = router_prefix.get((stem, var), "")
        inc = [p for target, p, _ in includes
               if target in {var, f"{stem}.{var}", f"{stem}_{var}", f"{stem}_router"} or target.endswith(f".{stem}.{var}")]
        if len(inc) > 1:
            notes.append(f"router `{stem}.{var}` included {len(inc)} times; using the first prefix")
        full = (inc[0] if inc else "") + prefix + path
        routes.append(Route(method, re.sub(r"/+", "/", full) or "/", where))
    for target, p, where in includes:
        stems = {s for s, *_ in raw}
        if not any(target.split(".")[0] in {s, v} or target.endswith(f"{s}_router") for s, v, *_ in raw) and stems:
            notes.append(f"`{where}`: include_router({target}, prefix={p!r}) not matched to a router; verify prefixes")
    return routes, notes


def norm_path(p: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", p.rstrip("/") or "/")


# ---------------------------------------------------------------- schema

def _split_top(s: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def parse_sql(files: list[Path], root: Path) -> tuple[dict[str, dict[str, Column]], dict[str, list[str]]]:
    tables: dict[str, dict[str, Column]] = {}
    enums: dict[str, list[str]] = {}
    for f in files:
        sql = re.sub(r"--[^\n]*", "", f.read_text(encoding="utf-8", errors="replace"))
        for m in re.finditer(r"CREATE\s+TYPE\s+([\w.\"]+)\s+AS\s+ENUM\s*\(([^)]*)\)", sql, re.I):
            enums[m.group(1).strip('"').lower()] = re.findall(r"'([^']*)'", m.group(2))
        for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)\s*\(", sql, re.I):
            start, depth, i = m.end(), 1, m.end()
            while i < len(sql) and depth:
                depth += {"(": 1, ")": -1}.get(sql[i], 0)
                i += 1
            body = sql[start:i - 1]
            name = m.group(1).strip('"').split(".")[-1].lower()
            cols = tables.setdefault(name, {})
            line = sql[: m.start()].count("\n") + 1
            for part in _split_top(body):
                tok = part.split()
                if not tok or tok[0].upper() in {"PRIMARY", "FOREIGN", "UNIQUE", "CONSTRAINT", "CHECK", "EXCLUDE"}:
                    cm = re.search(r"CHECK\s*\(\s*\"?(\w+)\"?\s+IN\s*\(([^)]*)\)", part, re.I)
                    if cm and cm.group(1).lower() in cols:
                        cols[cm.group(1).lower()].enum_values = re.findall(r"'([^']*)'", cm.group(2))
                    continue
                cname = tok[0].strip('"').lower()
                rest = " ".join(tok[1:])
                tm = re.match(r"(timestamp\s+with(?:out)?\s+time\s+zone|double\s+precision|character\s+varying(?:\(\d+\))?|"
                              r"[\w]+(?:\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)", rest, re.I)
                ctype = tm.group(1).lower() if tm else "?"
                tz = None
                if ctype.startswith("timestamp"):
                    tz = "with time zone" in ctype or ctype == "timestamptz"
                col = Column(cname, "enum" if ctype in enums else ctype, f"{f.relative_to(root)}:{line}", tz)
                if ctype in enums:
                    col.enum_values = enums[ctype]
                cm = re.search(r"CHECK\s*\(\s*\"?\w+\"?\s+IN\s*\(([^)]*)\)", part, re.I)
                if cm:
                    col.enum_values = re.findall(r"'([^']*)'", cm.group(1))
                cols[cname] = col
    return tables, enums


def parse_models(files: list[Path], root: Path) -> dict[str, dict[str, Column]]:
    tables: dict[str, dict[str, Column]] = {}
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        enum_classes: dict[str, list[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(_expr_key(b).endswith("Enum") for b in node.bases):
                enum_classes[node.name] = [s.value.value for s in node.body
                                           if isinstance(s, ast.Assign) and isinstance(s.value, ast.Constant)
                                           and isinstance(s.value.value, str)]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            tname = None
            for s in node.body:
                if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in s.targets):
                    tname = _const_str(s.value, {})
            if not tname:
                continue
            cols = tables.setdefault(tname.lower(), {})
            for s in node.body:
                target, value, ann = None, None, None
                if isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name):
                    target, value = s.targets[0].id, s.value
                elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
                    target, value, ann = s.target.id, s.value, s.annotation
                if not target or target.startswith("__"):
                    continue
                if not (isinstance(value, ast.Call) and _expr_key(value.func).split(".")[-1] in {"Column", "mapped_column"}):
                    if ann is None or "relationship" in (_expr_key(value) if value else ""):
                        continue
                ctype, tz, values = "?", None, []
                args = value.args if isinstance(value, ast.Call) else []
                type_arg = next((a for a in args if not (isinstance(a, ast.Constant) and isinstance(a.value, str))
                                 and "ForeignKey" not in _expr_key(a)), None)
                if type_arg is not None:
                    tcall = type_arg.func if isinstance(type_arg, ast.Call) else type_arg
                    ctype = _expr_key(tcall).split(".")[-1].lower()
                    if isinstance(type_arg, ast.Call):
                        tzkw = _kw(type_arg, "timezone")
                        if isinstance(tzkw, ast.Constant):
                            tz = bool(tzkw.value)
                        if ctype == "enum":
                            for a in type_arg.args:
                                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                                    values.append(a.value)
                                elif isinstance(a, ast.Name) and a.id in enum_classes:
                                    values.extend(enum_classes[a.id])
                elif ann is not None:
                    inner = _expr_key(ann)
                    m = re.search(r"Mapped\[(?:Optional\[)?([\w.]+)", inner)
                    ctype = (m.group(1).split(".")[-1].lower() if m else "?")
                    ctype = {"decimal": "numeric", "str": "string", "int": "integer"}.get(ctype, ctype)
                    if ctype in {k.lower() for k in enum_classes}:
                        values = next(v for k, v in enum_classes.items() if k.lower() == ctype)
                        ctype = "enum"
                if ctype in {"datetime", "timestamp"} and tz is None:
                    tz = False
                cols[target.lower()] = Column(target.lower(), ctype, f"{f.relative_to(root)}:{s.lineno}", tz, values)
    return tables


def canonical_enums() -> dict[str, set[str]]:
    sys.path.insert(0, str(REPO / "backend"))
    try:
        from trademind.domain import AssetClass, OrderStatus, OrderType, Side, Timeframe
    except Exception:  # pragma: no cover - package not installed
        return {}
    return {"side": {e.value for e in Side}, "status": {e.value for e in OrderStatus},
            "order_type": {e.value for e in OrderType}, "type": {e.value for e in OrderType},
            "asset_class": {e.value for e in AssetClass}, "timeframe": {e.value for e in Timeframe}}


# ---------------------------------------------------------------- misc

def env_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [m.group(1) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if (m := re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line))]


def requirements(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#")[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(.*)", line)
        if m and not line.startswith("-"):
            out[m.group(1).lower().replace("_", "-")] = m.group(3).strip()
    return out


def canonical_deps() -> dict[str, str]:
    text = CANONICAL_PYPROJECT.read_text(encoding="utf-8") if CANONICAL_PYPROJECT.exists() else ""
    out = {}
    for spec in re.findall(r'"([A-Za-z0-9_.\-]+(?:\[[^\]]*\])?[^"]*)"', text):
        m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?(.*)", spec)
        if m and re.search(r"[<>=~]", m.group(3) or ""):
            out[m.group(1).lower().replace("_", "-")] = m.group(3).strip()
    return out


def scan(files: list[Path], root: Path) -> list[Finding]:
    out = []
    for f in files:
        if f.suffix.lower() not in {".py", ".sql", ".toml", ".ini", ".cfg", ".yml", ".yaml", ".json", ".txt", ".md", ".ps1", ".sh", ".example", ""}:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for pat, label in BLOCKER_PATTERNS:
                if re.search(pat, line):
                    out.append(Finding("BLOCKER", "safety", f"`{f.relative_to(root)}:{n}` {label}"))
            for pat, label in WARN_PATTERNS:
                if re.search(pat, line):
                    out.append(Finding("WARN", "safety", f"`{f.relative_to(root)}:{n}` {label}"))
    return out


# ---------------------------------------------------------------- audit

def audit(mvp: Path) -> tuple[list[Finding], dict]:
    files = sorted(p for p in mvp.rglob("*") if p.is_file())
    py = [p for p in files if p.suffix == ".py"]
    app_py = [p for p in py if "tests" not in p.relative_to(mvp).parts and p.name != "conftest.py"]
    findings: list[Finding] = []
    ctx: dict = {"files": len(files)}

    # Routes
    mvp_routes, notes = extract_routes(app_py, mvp)
    ours, _ = extract_routes([CANONICAL_API], REPO)
    our_index = {(r.method, norm_path(r.path)): r for r in ours}
    ctx["route_notes"] = notes
    ctx["routes"] = []
    for r in sorted(mvp_routes, key=lambda r: (r.path, r.method)):
        hit = our_index.get((r.method, norm_path(r.path)))
        status = "COLLISION" if hit else "MVP only, port onto canonical router"
        ctx["routes"].append((r, hit, status))
        if hit:
            findings.append(Finding("CONFLICT", "api", f"`{r.method} {r.path}` exists in both "
                                    f"(MVP `{r.where}`, canonical `{hit.where}`); keep canonical, make its response a superset"))
    ctx["canonical_routes"] = ours

    # Schema
    sql_files = [p for p in files if p.suffix.lower() == ".sql"]
    sql_tables, _ = parse_sql(sql_files, mvp)
    model_tables = parse_models([p for p in app_py if p.stem in {"models", "db", "tables"}
                                 or "models" in p.relative_to(mvp).parts], mvp)
    ctx["sql_tables"], ctx["model_tables"] = sql_tables, model_tables
    for t in sorted(set(sql_tables) - set(model_tables)):
        if model_tables:
            findings.append(Finding("CONFLICT", "schema", f"table `{t}` is in SQL migrations but has no SQLAlchemy model"))
    for t in sorted(set(model_tables) - set(sql_tables)):
        if sql_tables:
            findings.append(Finding("CONFLICT", "schema", f"model table `{t}` has no SQL migration"))
    for t in sorted(set(sql_tables) & set(model_tables)):
        for c in sorted(set(sql_tables[t]) | set(model_tables[t])):
            a, b = sql_tables[t].get(c), model_tables[t].get(c)
            if a is None or b is None:
                findings.append(Finding("CONFLICT", "schema", f"`{t}.{c}` only in {'model' if a is None else 'SQL'}"))
            elif family(a.type) != family(b.type) and "?" not in (family(a.type), family(b.type)):
                findings.append(Finding("CONFLICT", "schema",
                                        f"`{t}.{c}` type differs: SQL `{a.type}` vs model `{b.type}`"))
    enums = canonical_enums()
    for source, tables in (("SQL", sql_tables), ("model", model_tables)):
        for t, cols in tables.items():
            for c in cols.values():
                fam = family(c.type)
                if fam == "float" and MONEY_COL.search(c.name):
                    findings.append(Finding("WARN", "schema", f"{source} `{t}.{c.name}` is `{c.type}`; canonical money/size "
                                            "values are Decimal, use NUMERIC"))
                if fam == "datetime" and c.tz is False:
                    findings.append(Finding("WARN", "schema", f"{source} `{t}.{c.name}` is timezone-naive; canonical "
                                            "timestamps are UTC-aware, use TIMESTAMPTZ / DateTime(timezone=True)"))
                key = c.name if c.name in enums else c.name.removeprefix("order_")
                if c.enum_values and key in enums:
                    vals = {v.lower() if key != "timeframe" else v for v in c.enum_values}
                    if vals != enums[key]:
                        missing, extra = sorted(enums[key] - vals), sorted(vals - enums[key])
                        findings.append(Finding("CONFLICT", "schema",
                                                f"{source} `{t}.{c.name}` values {sorted(c.enum_values)} differ from canonical "
                                                f"{sorted(enums[key])} (missing {missing}, extra {extra})"))
                    elif any(v != v.lower() for v in c.enum_values) and key != "timeframe":
                        findings.append(Finding("WARN", "schema", f"{source} `{t}.{c.name}` uses upper-case values "
                                                f"{c.enum_values}; canonical values are lower-case"))

    # Duplicate implementations
    ctx["duplicates"] = []
    for p in app_py:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        home = CANONICAL_HOMES.get(p.stem)
        if home:
            ctx["duplicates"].append((p.relative_to(mvp), home, defs))
        ind = sorted({d for d in defs if d.lower() in INDICATOR_FUNCS})
        if ind and p.stem != "strategy":
            findings.append(Finding("CONFLICT", "duplicate", f"`{p.relative_to(mvp)}` defines indicators {ind}; "
                                    "use backend/trademind/indicators.py instead"))
        elif ind:
            findings.append(Finding("CONFLICT", "duplicate", f"`{p.relative_to(mvp)}` re-implements indicators {ind}; "
                                    "port strategy logic onto backend/trademind/indicators.py"))
        if p.stem in {"risk", "paper", "strategy"}:
            findings.append(Finding("CONFLICT", "duplicate", f"`{p.relative_to(mvp)}` duplicates {CANONICAL_HOMES[p.stem]}; "
                                    "merge its rules/tests into the canonical module, do not import it"))

    findings += scan(files, mvp)

    # Env & dependencies
    mvp_env = []
    for name in (".env.example", "backend/.env.example"):
        mvp_env += env_keys(mvp / name)
    ours_env = set(env_keys(CANONICAL_ENV))
    ctx["env"] = [(k, f"TRADEMIND_{k.upper()}" if f"TRADEMIND_{k.upper()}" in ours_env else None)
                  for k in dict.fromkeys(mvp_env)]
    reqs = {}
    for p in files:
        if p.name.startswith("requirements") and p.suffix == ".txt":
            reqs.update(requirements(p))
    ours_deps = canonical_deps()
    ctx["deps"] = [(name, spec, ours_deps.get(name)) for name, spec in sorted(reqs.items())]
    return findings, ctx


def render(mvp: Path, findings: list[Finding], ctx: dict) -> str:
    order = {"BLOCKER": 0, "CONFLICT": 1, "WARN": 2, "INFO": 3}
    findings = sorted(findings, key=lambda f: (order[f.severity], f.area, f.message))
    count = {s: sum(f.severity == s for f in findings) for s in order}
    L = ["# MVP Integration Report", "",
         f"Generated by `scripts/mvp_audit.py` from `{mvp.name}` ({ctx['files']} files). Static analysis only; "
         "MVP code was not executed. Regenerate after every porting step.", "",
         f"**{count['BLOCKER']} blocker(s), {count['CONFLICT']} conflict(s), {count['WARN']} warning(s).** "
         "Blockers must be removed before the MVP code is merged into any branch that deploys.", ""]
    L += ["## Findings", ""]
    if not findings:
        L.append("None.")
    for f in findings:
        L.append(f"- **{f.severity}** [{f.area}] {f.message}")
    L += ["", "## API routes", "", "| Method | MVP path | MVP location | Status |", "|---|---|---|---|"]
    for r, _hit, status in ctx["routes"]:
        L.append(f"| {r.method} | `{r.path}` | `{r.where}` | {status} |")
    if not ctx["routes"]:
        L.append("| | (no FastAPI routes found) | | |")
    L += ["", "Canonical routes: " + ", ".join(f"`{r.method} {r.path}`" for r in ctx["canonical_routes"]) + "."]
    for n in ctx["route_notes"]:
        L.append(f"- Note: {n}")
    L += ["", "## Database schema", ""]
    for label, tables in (("SQL migrations", ctx["sql_tables"]), ("SQLAlchemy models", ctx["model_tables"])):
        L.append(f"**{label}:** " + (", ".join(f"`{t}` ({len(c)} cols)" for t, c in sorted(tables.items())) or "none found"))
        L.append("")
    L += ["The integrated codebase has no database yet, so the MVP schema becomes the Alembic baseline once the "
          "conflicts above are resolved.", "", "## Modules that overlap canonical code", "",
          "| MVP file | Canonical home | Top-level definitions |", "|---|---|---|"]
    for rel, home, defs in sorted(ctx["duplicates"], key=lambda x: str(x[0])):
        L.append(f"| `{rel}` | {home} | {', '.join(f'`{d}`' for d in defs) or '—'} |")
    L += ["", "## Environment variables", "", "| MVP key | Canonical key |", "|---|---|"]
    for k, ours in ctx["env"]:
        L.append(f"| `{k}` | {f'`{ours}`' if ours else 'none: add as `TRADEMIND_*` or drop'} |")
    L += ["", "## Dependencies (MVP requirements vs backend/pyproject.toml)", "", "| Package | MVP | Canonical |", "|---|---|---|"]
    for name, spec, ours in ctx["deps"]:
        L.append(f"| {name} | `{spec or 'unpinned'}` | {f'`{ours}`' if ours else 'not a dependency yet'} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mvp", type=Path, help="imported MVP directory, e.g. legacy/mvp")
    ap.add_argument("--out", type=Path, default=REPO / "docs" / "MVP_INTEGRATION_REPORT.md")
    a = ap.parse_args(argv)
    if not a.mvp.is_dir():
        print(f"not a directory: {a.mvp}", file=sys.stderr)
        return 2
    findings, ctx = audit(a.mvp.resolve())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(a.mvp.resolve(), findings, ctx), encoding="utf-8")
    blockers = [f for f in findings if f.severity == "BLOCKER"]
    conflicts = sum(f.severity == "CONFLICT" for f in findings)
    print(f"Report: {a.out}  ({len(blockers)} blockers, {conflicts} conflicts)")
    for f in blockers:
        print(f"BLOCKER {f.message}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
