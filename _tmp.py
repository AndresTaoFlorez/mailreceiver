import asyncio, asyncpg

async def main():
    conn = await asyncpg.connect(
        host="159.223.160.218", port=5432,
        user="mailreceiver", password="D4t4SGD*3_RW",
        database="mailreceiver",
    )
    print("=== folder_config for justicia_xxi_web ===")
    rows = await conn.fetch("""
        SELECT folder_name, level, especialist_id, active
        FROM folder_config
        WHERE application_code = 'justicia_xxi_web'
        ORDER BY especialist_id NULLS FIRST, level
    """)
    if not rows:
        print("  (none)")
    for r in rows:
        ftype = "analyst" if r["especialist_id"] else "level"
        print(f"  [{ftype}] {r['folder_name']!r} level={r['level']} active={r['active']}")

    print("\n=== conversations folders for justicia_xxi_web ===")
    rows = await conn.fetch("""
        SELECT folder, level, COUNT(*) as cnt
        FROM conversations
        WHERE app = 'justicia_xxi_web'
        GROUP BY folder, level ORDER BY folder
    """)
    for r in rows:
        print(f"  folder={r['folder']!r} level={r['level']} count={r['cnt']}")

    await conn.close()

asyncio.run(main())
