"""Writes db_tables.md: a table-by-table list of columns, keys and delete rules.
Paste it into your report (Database design section)."""
from db import get_connection

conn = get_connection()
tables = [r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

out = ["# E-Mart: tables, keys and relationships\n"]
for t in tables:
    fks = {fk["from"]: fk for fk in conn.execute(f"PRAGMA foreign_key_list({t})")}
    out.append(f"## {t}\n")
    out.append("| Column | Type | Key | NOT NULL | Default | References (ON DELETE) |")
    out.append("|---|---|---|---|---|---|")
    for c in conn.execute(f"PRAGMA table_info({t})"):
        key = ["PK"] if c["pk"] else []
        fk = fks.get(c["name"])
        if fk:
            key.append("FK")
        ref = f'{fk["table"]}.{fk["to"]} ({fk["on_delete"]})' if fk else ""
        out.append(f'| {c["name"]} | {c["type"]} | {", ".join(key)} | '
                   f'{"yes" if c["notnull"] else ""} | {c["dflt_value"] or ""} | {ref} |')
    out.append("")

open("db_tables.md", "w", encoding="utf-8").write("\n".join(out))
print("Wrote db_tables.md")