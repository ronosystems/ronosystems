"""
Restore old data from db.sqlite3.backup into the new Option B schema.
Run: python restore_old_data.py
"""

"""
ARCHIVED — one-time migration script used on 2026-11-12 to migrate
Phone/Electronic/Accessory stock fields into the new Unit + BranchStock
model. Migrations 0022–0024 already applied this change to production.

DO NOT RUN against the current schema.
"""
import sqlite3
import os

OLD = "db.sqlite3.backup"
NEW = "db.sqlite3"

if not os.path.exists(OLD):
    raise SystemExit(f"❌ {OLD} not found. Abort.")
if not os.path.exists(NEW):
    raise SystemExit(f"❌ {NEW} not found. Abort.")

old = sqlite3.connect(OLD)
new = sqlite3.connect(NEW)
old.row_factory = sqlite3.Row
new.row_factory = sqlite3.Row

old_cur = old.cursor()
new_cur = new.cursor()

def table_exists(cur, name):
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def get_columns(cur, table):
    cur.execute(f"PRAGMA table_info({table})")
    return [r["name"] for r in cur.fetchall()]

def copy_table(table):
    if not table_exists(old_cur, table):
        print(f"  ⚠️  {table} does not exist in OLD - skipping")
        return 0
    if not table_exists(new_cur, table):
        print(f"  ⚠️  {table} does not exist in NEW - skipping")
        return 0

    old_cols = set(get_columns(old_cur, table))
    new_cols = set(get_columns(new_cur, table))
    common = sorted(old_cols & new_cols)

    if not common:
        print(f"  ⚠️  {table}: no common columns - skipping")
        return 0

    old_cur.execute(f"SELECT {', '.join(common)} FROM {table}")
    rows = old_cur.fetchall()

    placeholders = ", ".join("?" * len(common))
    cols_sql = ", ".join(common)
    sql = f"INSERT OR REPLACE INTO {table} ({cols_sql}) VALUES ({placeholders})"

    count = 0
    for row in rows:
        try:
            new_cur.execute(sql, tuple(row))
            count += 1
        except sqlite3.IntegrityError as e:
            print(f"  ⚠️  {table}: row skipped ({e})")
    print(f"  ✅ {table}: {count} rows")
    return count

print("\n[1/4] Wiping test data from NEW db...")
tables_to_wipe = [
    "epa_branch_stocks", "epa_stock_transfers", "epa_stock_movements",
    "epa_sale_items", "epa_sales", "epa_phones", "epa_electronics",
    "epa_accessories", "epa_units", "epa_categories", "epa_suppliers",
    "epa_owners", "epa_customers", "epa_purchase_orders",
    "epa_purchase_order_items", "epa_warranties", "epa_repairs",
    "finance_cogs_accounts", "finance_cogs_transactions",
    "finance_cogs_allocation_rules", "finance_cogs_summaries",
    "finance_purchase_records", "rono_business_types",
    "epa_return_items",
    "rono_users", "epa_branches", "rono_companies",
    "rono_company_join_requests", "rono_support_sessions",
]
for t in tables_to_wipe:
    if table_exists(new_cur, t):
        new_cur.execute(f"DELETE FROM {t}")
new.commit()
print("  ✅ Wiped.")

print("\n[2/4] Copying flat tables...")
flat_tables = [
    "rono_business_types",
    "rono_companies",
    "rono_company_join_requests",
    "rono_support_sessions",
    "epa_branches",
    "rono_users",
    "epa_categories",
    "epa_suppliers",
    "epa_owners",
    "epa_customers",
    "epa_purchase_orders",
    "epa_purchase_order_items",
    "epa_warranties",
    "epa_repairs",
    "finance_cogs_accounts",
    "finance_cogs_transactions",
    "finance_cogs_allocation_rules",
    "finance_cogs_summaries",
    "finance_purchase_records",
]
for t in flat_tables:
    copy_table(t)

print("\n[3/4] Copying sales...")
copy_table("epa_sales")
copy_table("epa_sale_items")
copy_table("epa_units")
copy_table("epa_stock_movements")

print("\n[4/4] Copying products and rebuilding BranchStock...")
PRODUCT_TABLES = [
    ("epa_phones", "phone"),
    ("epa_electronics", "electronic"),
    ("epa_accessories", "accessory"),
]

for table, model_name in PRODUCT_TABLES:
    if not table_exists(old_cur, table):
        print(f"  ⚠️  {table} missing in OLD")
        continue

    old_cols = get_columns(old_cur, table)
    new_cols = get_columns(new_cur, table)
    SKIP = {"branch_id", "quantity_in_stock", "minimum_stock_level", "maximum_stock_level", "total_quantity_in_stock"}
    copy_cols = [c for c in old_cols if c in new_cols and c not in SKIP]

    old_cur.execute(f"SELECT * FROM {table}")
    rows = old_cur.fetchall()

    product_count = 0
    branchstock_count = 0

    for row in rows:
        row = dict(row)
        insert_sql = f"INSERT OR REPLACE INTO {table} ({', '.join(copy_cols)}, total_quantity_in_stock) VALUES ({', '.join(['?']*len(copy_cols))}, ?)"
        new_cur.execute(insert_sql, [row[c] for c in copy_cols] + [0])
        product_count += 1

        old_branch = row.get("branch_id")
        old_qty = row.get("quantity_in_stock") or 0
        old_min = row.get("minimum_stock_level") or 2
        old_max = row.get("maximum_stock_level") or 100
        if not old_branch:
            continue

        # Verify the branch exists in NEW db before creating BranchStock
        new_cur.execute("SELECT id FROM epa_branches WHERE id=?", (old_branch,))
        if not new_cur.fetchone():
            print(f"  ⚠️  {table} id={row['id']}: branch_id={old_branch} not found in NEW - skipping BranchStock row")
            continue

        new_cur.execute(
            "SELECT id FROM django_content_type WHERE app_label='epa_shop' AND model=?",
            (model_name,),
        )
        ct_row = new_cur.fetchone()
        if not ct_row:
            print(f"  ⚠️  content_type for {model_name} missing")
            continue
        ct_id = ct_row["id"]

        new_cur.execute("""
            INSERT OR REPLACE INTO epa_branch_stocks
              (branch_id, company_id, content_type_id, object_id,
               quantity_in_stock, minimum_stock_level, maximum_stock_level, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (old_branch, row["company_id"], ct_id, row["id"],
              old_qty, old_min, old_max))
        branchstock_count += 1

        new_cur.execute(
            f"UPDATE {table} SET total_quantity_in_stock = ? WHERE id = ?",
            (old_qty, row["id"]),
        )

    print(f"  ✅ {table}: {product_count} products, {branchstock_count} BranchStock rows")

new.commit()
print("\n🎉 RESTORE COMPLETE")

old.close()
new.close()
