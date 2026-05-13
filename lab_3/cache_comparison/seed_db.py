import argparse
import json
import random
import sqlite3
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--keys", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    rnd = random.Random(int(args.seed))
    conn = sqlite3.connect(args.db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """.strip()
    )

    now = time.time()
    rows = []
    for i in range(int(args.keys)):
        item_id = f"item-{i}"
        value = {"n": rnd.randint(0, 1_000_000), "v": f"seed-{i}"}
        value_json = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        rows.append((item_id, value_json, now))

    conn.executemany(
        """
        INSERT INTO items(id, value_json, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at
        """.strip(),
        rows,
    )
    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

