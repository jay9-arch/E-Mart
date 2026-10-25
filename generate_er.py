from db import get_connection

conn = get_connection()
tables = [r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]

lines, rels = ["erDiagram"], []
for t in tables:
    fks = list(conn.execute(f"PRAGMA foreign_key_list({t})"))
    fk_cols = {fk["from"] for fk in fks}
    lines.append(f"    {t} {{")
    for c in conn.execute(f"PRAGMA table_info({t})"):
        keys = (["PK"] if c["pk"] else []) + (["FK"] if c["name"] in fk_cols else [])
        lines.append(f"        {c['type'] or 'TEXT'} {c['name']} {', '.join(keys)}".rstrip())
    lines.append("    }")
    for fk in fks:
        rels.append(f'    {fk["table"]} ||--o{{ {t} : "{fk["from"]}"')

text = "\n".join(lines + rels)
open("er_diagram.mmd", "w", encoding="utf-8").write(text)
print(text)