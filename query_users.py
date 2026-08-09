"""
Query the production users table on Render Postgres.

Usage:
  1. Get the EXTERNAL Database URL from your database's Connections
     section in the Render dashboard (the internal URL won't work
     from your computer).
  2. Set it as an environment variable, then run the script:

     PowerShell:
       $env:PROD_DATABASE_URL = "postgresql://user:pass@host.oregon-postgres.render.com/dbname"
       python query_users.py

  Results print to the console and are saved to users_export.xlsx.
"""
import os
import sys

import pandas as pd
from sqlalchemy import create_engine

url = os.environ.get("PROD_DATABASE_URL")
if not url:
    url = input("Paste your External Database URL: ").strip()

# Render sometimes shows postgres:// — SQLAlchemy needs postgresql://
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url, connect_args={"connect_timeout": 10, "sslmode": "require"})

QUERY = """
SELECT
    u.email,
    u.first_name,
    u.last_name,
    u.state,
    u.favorite_sport,
    u.favorite_teams,
    u.created_at,
    u.trial_ends_at,
    s.status AS subscription_status
FROM users u
LEFT JOIN subscriptions s ON s.user_id = u.id
ORDER BY u.created_at DESC;
"""

try:
    df = pd.read_sql(QUERY, engine)
except Exception as e:
    sys.exit(f"Query failed: {e}")

print(f"\n{len(df)} users found\n")
print(df.to_string(index=False))

# Quick breakdowns
for col in ["state", "favorite_sport", "subscription_status"]:
    if df[col].notna().any():
        print(f"\n--- Users by {col} ---")
        print(df[col].value_counts(dropna=False).to_string())

df.to_excel("users_export.xlsx", index=False)
print("\nSaved to users_export.xlsx")
