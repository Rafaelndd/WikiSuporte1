#!/usr/bin/env python3
"""
Compara schema (e opcionalmente contagens) entre PostgreSQL V1 e V2 para montar de-para.

Redes diferentes / sem acesso simultâneo:
  1) Exportar snapshot em cada ambiente (máquina que alcança só aquele banco):
       python scripts/depara_schema_compare.py export-snapshot --out v1_schema.json --database-url "postgresql://..."
       python scripts/depara_schema_compare.py export-snapshot --out v2_schema.json --database-url "postgresql://..."
  2) Copiar os JSON para um único computador e comparar offline:
       python scripts/depara_schema_compare.py compare --source-snapshot v1_schema.json --target-snapshot v2_schema.json

Acesso simultâneo (VPN, túnel SSH, bastion com port-forward para os dois):
       python scripts/depara_schema_compare.py compare --source-url "$V1_URL" --target-url "$V2_URL"

Túnel SSH exemplo (V1 em rede A, você no laptop):
       ssh -L 15432:v1-db.internal:5432 usuario@bastion-a
       export V1_URL=postgresql://user:pass@127.0.0.1:15432/wikisuporte

Requisitos: SQLAlchemy + psycopg2 (já no projeto WikiSuporte).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


DEFAULT_SCHEMAS = ("public",)


def _norm_name(s: str) -> str:
    t = re.sub(r"\s+", "_", str(s or "").strip().lower())
    return re.sub(r"[^a-z0-9_]", "", t)


def _similarity(a: str, b: str) -> float:
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _table_key(schema: str, table: str) -> str:
    return f'{schema}.{table}' if schema != "public" else table


@dataclass
class ColumnInfo:
    column_name: str
    data_type: str
    udt_name: str
    is_nullable: str
    column_default: Optional[str]

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)


def fetch_columns(engine: Engine, schemas: Sequence[str]) -> Dict[str, List[ColumnInfo]]:
    q = text(
        """
        SELECT table_schema, table_name, column_name, data_type, udt_name,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = ANY(:schemas)
        ORDER BY table_schema, table_name, ordinal_position
        """
    )
    out: Dict[str, List[ColumnInfo]] = {}
    with engine.connect() as conn:
        rows = conn.execute(q, {"schemas": list(schemas)}).mappings().all()
    for r in rows:
        key = _table_key(str(r["table_schema"]), str(r["table_name"]))
        col = ColumnInfo(
            column_name=str(r["column_name"]),
            data_type=str(r["data_type"]),
            udt_name=str(r["udt_name"] or ""),
            is_nullable=str(r["is_nullable"]),
            column_default=r["column_default"],
        )
        out.setdefault(key, []).append(col)
    return out


def fetch_tables(engine: Engine, schemas: Sequence[str]) -> List[Tuple[str, str]]:
    q = text(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = ANY(:schemas)
          AND table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(q, {"schemas": list(schemas)}).fetchall()
    return [(str(a), str(b)) for a, b in rows]


def fetch_row_estimates(engine: Engine, schemas: Sequence[str]) -> Dict[str, Optional[int]]:
    """Usa pg_stat_user_tables quando disponível (estimativa rápida)."""
    q = text(
        """
        SELECT schemaname, relname, n_live_tup::bigint AS estimate
        FROM pg_stat_user_tables
        WHERE schemaname = ANY(:schemas)
        """
    )
    out: Dict[str, Optional[int]] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(q, {"schemas": list(schemas)}).mappings().all()
        for r in rows:
            key = _table_key(str(r["schemaname"]), str(r["relname"]))
            est = r.get("estimate")
            out[key] = int(est) if est is not None else None
    except Exception:
        pass
    return out


def schema_to_snapshot(
    engine: Engine,
    schemas: Sequence[str],
    label: str,
    include_estimates: bool,
) -> Dict[str, Any]:
    cols = fetch_columns(engine, schemas)
    tables = fetch_tables(engine, schemas)
    estimates: Dict[str, Any] = {}
    if include_estimates:
        estimates = fetch_row_estimates(engine, schemas)
    snap = {
        "meta": {
            "label": label,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "schemas": list(schemas),
        },
        "tables": [{"schema": s, "table": t, "full_name": _table_key(s, t)} for s, t in tables],
        "columns_by_table": {k: [c.to_json() for c in v] for k, v in cols.items()},
        "row_estimates": estimates,
    }
    return snap


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def suggest_table_mapping(
    source_tables: List[str],
    target_tables: List[str],
    threshold: float,
    hints: Optional[Dict[str, str]] = None,
) -> Dict[str, Optional[str]]:
    """
    Retorna mapa source_table -> target_table ou None se não há match acima do threshold.
    hints: {"atendimentos_registrados": "support_tickets"} força pares.
    """
    hints = hints or {}
    src_set = list(source_tables)
    tgt_set = list(target_tables)
    used_tgt = set()
    mapping: Dict[str, Optional[str]] = {}

    for s in src_set:
        if s in hints and hints[s] in tgt_set:
            mapping[s] = hints[s]
            used_tgt.add(hints[s])
        else:
            mapping[s] = None

    for s in src_set:
        if mapping.get(s):
            continue
        best: Tuple[float, Optional[str]] = (0.0, None)
        for t in tgt_set:
            if t in used_tgt:
                continue
            score = _similarity(s, t)
            if score > best[0]:
                best = (score, t)
        if best[0] >= threshold and best[1]:
            mapping[s] = best[1]
            used_tgt.add(best[1])
        else:
            mapping[s] = mapping.get(s)  # pode já ter sido forçado

    return mapping


def columns_dict_from_snapshot_table(
    snap: Dict[str, Any], table_key: str
) -> Dict[str, ColumnInfo]:
    raw = snap.get("columns_by_table", {}).get(table_key, [])
    out: Dict[str, ColumnInfo] = {}
    for r in raw:
        c = ColumnInfo(
            column_name=r["column_name"],
            data_type=r["data_type"],
            udt_name=r.get("udt_name", ""),
            is_nullable=r.get("is_nullable", ""),
            column_default=r.get("column_default"),
        )
        out[_norm_name(c.column_name)] = c
    return out


def compare_columns(
    source_cols: Dict[str, ColumnInfo],
    target_cols: Dict[str, ColumnInfo],
    fuzzy_threshold: float,
) -> Tuple[Dict[str, str], List[str], List[str], List[str]]:
    """
    Para cada coluna fonte (por nome normalizado), sugere coluna destino.
    Retorna: (mapping_norm_src_to_tgt, missing_in_target, extra_in_target, type_warnings)
    """
    mapping: Dict[str, str] = {}
    used_tgt_norm = set()

    tgt_by_norm = {k: v for k, v in target_cols.items()}

    for sn, sc in source_cols.items():
        if sn in tgt_by_norm:
            mapping[sn] = sn
            used_tgt_norm.add(sn)
            continue
        best: Tuple[float, Optional[str]] = (0.0, None)
        for tn, _ in target_cols.items():
            if tn in used_tgt_norm:
                continue
            score = _similarity(sc.column_name, target_cols[tn].column_name)
            if score > best[0]:
                best = (score, tn)
        if best[0] >= fuzzy_threshold and best[1]:
            mapping[sn] = best[1]
            used_tgt_norm.add(best[1])

    missing_in_target: List[str] = []
    for sn, sc in source_cols.items():
        if sn not in mapping:
            missing_in_target.append(sc.column_name)

    mapped_tgt_norms = set(mapping.values())
    extra_in_target = [
        target_cols[t].column_name for t in target_cols if t not in mapped_tgt_norms
    ]

    type_warnings: List[str] = []
    for sn, tn in mapping.items():
        if sn not in source_cols or tn not in target_cols:
            continue
        s_col, t_col = source_cols[sn], target_cols[tn]
        if _norm_name(s_col.data_type) != _norm_name(t_col.data_type) or _norm_name(s_col.udt_name) != _norm_name(
            t_col.udt_name
        ):
            type_warnings.append(
                f"{s_col.column_name} ({s_col.data_type}/{s_col.udt_name}) -> "
                f"{t_col.column_name} ({t_col.data_type}/{t_col.udt_name})"
            )

    return mapping, missing_in_target, extra_in_target, type_warnings


def run_interactive_table_fix(
    unmapped_sources: List[str],
    target_tables: List[str],
) -> Dict[str, str]:
    """Solicita confirmação no terminal para tabelas sem par automático."""
    fixes: Dict[str, str] = {}
    if not unmapped_sources:
        return fixes
    print("\n=== Validação manual: tabelas de origem sem destino automático ===\n")
    for s in unmapped_sources:
        print(f"Origem: {s}")
        print("  Destinos possíveis (número) ou Enter para pular:")
        for i, t in enumerate(target_tables[:80], 1):
            print(f"    [{i}] {t}")
        if len(target_tables) > 80:
            print(f"    ... (+{len(target_tables) - 80} outras; edite o JSON gerado)")
        choice = input("  Escolha o número (vazio=pular): ").strip()
        if not choice:
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(target_tables):
                fixes[s] = target_tables[idx]
        except ValueError:
            pass
    return fixes


def build_compare_payload(
    source_snap: Dict[str, Any],
    target_snap: Dict[str, Any],
    table_threshold: float,
    column_threshold: float,
    table_hints: Optional[Dict[str, str]] = None,
    interactive_tables: bool = False,
) -> Dict[str, Any]:
    src_tables = [t["full_name"] for t in source_snap.get("tables", [])]
    tgt_tables = [t["full_name"] for t in target_snap.get("tables", [])]

    table_map = suggest_table_mapping(src_tables, tgt_tables, table_threshold, table_hints)
    unmapped = [s for s, t in table_map.items() if not t]
    manual: Dict[str, str] = {}
    if interactive_tables and unmapped:
        manual = run_interactive_table_fix(unmapped, tgt_tables)
        for s, t in manual.items():
            table_map[s] = t

    per_table: List[Dict[str, Any]] = []
    for src_t, tgt_t in sorted(table_map.items()):
        if not tgt_t:
            per_table.append(
                {
                    "source_table": src_t,
                    "target_table": None,
                    "status": "NO_TARGET",
                    "source_row_estimate": source_snap.get("row_estimates", {}).get(src_t),
                }
            )
            continue
        s_cols = columns_dict_from_snapshot_table(source_snap, src_t)
        t_cols = columns_dict_from_snapshot_table(target_snap, tgt_t)
        col_map, missing, extra, type_warn = compare_columns(s_cols, t_cols, column_threshold)
        src_est = source_snap.get("row_estimates", {}).get(src_t)
        tgt_est = target_snap.get("row_estimates", {}).get(tgt_t)
        per_table.append(
            {
                "source_table": src_t,
                "target_table": tgt_t,
                "status": "OK" if not missing else "MISSING_COLUMNS_IN_TARGET",
                "source_row_estimate": src_est,
                "target_row_estimate": tgt_est,
                "column_map_suggested": col_map,
                "source_columns_missing_in_target": missing,
                "target_columns_not_filled_by_source": extra,
                "type_mismatch_warnings": type_warn,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_meta": source_snap.get("meta"),
        "target_meta": target_snap.get("meta"),
        "table_mapping": table_map,
        "table_mapping_manual_overrides": manual,
        "details": per_table,
    }


def write_markdown_report(path: str, payload: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Relatório de-para V1 → V2 (schema)")
    lines.append("")
    lines.append(f"Gerado em: `{payload.get('generated_at')}`")
    lines.append("")
    src_m = payload.get("source_meta") or {}
    tgt_m = payload.get("target_meta") or {}
    lines.append("## Metadados")
    lines.append(f"- Origem: {src_m.get('label', '?')} — schemas {src_m.get('schemas')}")
    lines.append(f"- Destino: {tgt_m.get('label', '?')} — schemas {tgt_m.get('schemas')}")
    lines.append("")
    lines.append("## Resumo por tabela")
    lines.append("")
    lines.append("| Origem | Destino | Status | Est. linhas origem | Est. linhas destino | Colunas origem sem par no destino |")
    lines.append("|--------|---------|--------|--------------------|---------------------|-----------------------------------|")
    for row in payload.get("details", []):
        miss = row.get("source_columns_missing_in_target") or []
        miss_s = ", ".join(miss[:5]) + ("…" if len(miss) > 5 else "")
        lines.append(
            f"| {row.get('source_table')} | {row.get('target_table') or '—'} | {row.get('status')} | "
            f"{row.get('source_row_estimate')} | {row.get('target_row_estimate') or '—'} | {miss_s or '—'} |"
        )
    lines.append("")
    lines.append("## Avisos de tipo (amostra)")
    lines.append("")
    for row in payload.get("details", []):
        warns = row.get("type_mismatch_warnings") or []
        if not warns:
            continue
        lines.append(f"### `{row.get('source_table')}` → `{row.get('target_table')}`")
        for w in warns[:20]:
            lines.append(f"- {w}")
        if len(warns) > 20:
            lines.append(f"- … (+{len(warns) - 20} outros no JSON)")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_hints(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in data.items():
        out[str(k)] = str(v)
    return out


def cmd_export(args: argparse.Namespace) -> int:
    eng = create_engine(args.database_url, pool_pre_ping=True)
    snap = schema_to_snapshot(eng, tuple(args.schemas), args.label, include_estimates=not args.no_estimates)
    save_json(args.out, snap)
    print(f"Snapshot salvo em {args.out} ({len(snap.get('tables', []))} tabelas).")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    if args.source_snapshot and args.target_snapshot:
        source_snap = load_json(args.source_snapshot)
        target_snap = load_json(args.target_snapshot)
    elif args.source_url and args.target_url:
        s_eng = create_engine(args.source_url, pool_pre_ping=True)
        t_eng = create_engine(args.target_url, pool_pre_ping=True)
        source_snap = schema_to_snapshot(s_eng, tuple(args.schemas), args.source_label, include_estimates=not args.no_estimates)
        target_snap = schema_to_snapshot(t_eng, tuple(args.schemas), args.target_label, include_estimates=not args.no_estimates)
    else:
        print("Use --source-snapshot + --target-snapshot OU --source-url + --target-url", file=sys.stderr)
        return 2

    hints = parse_hints(args.table_hints)
    payload = build_compare_payload(
        source_snap,
        target_snap,
        table_threshold=args.table_threshold,
        column_threshold=args.column_threshold,
        table_hints=hints,
        interactive_tables=args.interactive,
    )
    save_json(args.out_json, payload)
    write_markdown_report(args.out_md, payload)
    print(f"JSON: {args.out_json}")
    print(f"Markdown: {args.out_md}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="De-para de schema PostgreSQL V1/V2")
    sub = parser.add_subparsers(dest="command", required=True)

    p_exp = sub.add_parser("export-snapshot", help="Exporta schema + estimativas para JSON (use em cada rede)")
    p_exp.add_argument("--database-url", required=True, help="postgresql://user:pass@host:port/db")
    p_exp.add_argument("--out", required=True, help="Arquivo JSON de saída")
    p_exp.add_argument("--label", default="database", help="Rótulo no meta")
    p_exp.add_argument("--schemas", nargs="+", default=list(DEFAULT_SCHEMAS))
    p_exp.add_argument("--no-estimates", action="store_true", help="Não consultar pg_stat_user_tables")
    p_exp.set_defaults(func=cmd_export)

    p_cmp = sub.add_parser("compare", help="Compara dois snapshots ou duas URLs")
    p_cmp.add_argument("--source-snapshot")
    p_cmp.add_argument("--target-snapshot")
    p_cmp.add_argument("--source-url", help="URL SQLAlchemy V1")
    p_cmp.add_argument("--target-url", help="URL SQLAlchemy V2")
    p_cmp.add_argument("--source-label", default="v1")
    p_cmp.add_argument("--target-label", default="v2")
    p_cmp.add_argument("--schemas", nargs="+", default=list(DEFAULT_SCHEMAS))
    p_cmp.add_argument("--no-estimates", action="store_true")
    p_cmp.add_argument("--table-threshold", type=float, default=0.72, help="Similaridade mínima para parear tabelas")
    p_cmp.add_argument("--column-threshold", type=float, default=0.85, help="Similaridade mínima para parear colunas")
    p_cmp.add_argument("--table-hints", help="JSON {\"base_conhecimento\":\"knowledge_items\"} força pares")
    p_cmp.add_argument("--interactive", action="store_true", help="Pergunta no terminal tabelas sem match")
    p_cmp.add_argument("--out-json", default="de_para_report.json")
    p_cmp.add_argument("--out-md", default="de_para_report.md")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
