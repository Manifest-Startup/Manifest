#!/usr/bin/env python3
"""
Supabase to Replit PostgreSQL Migration Script

This script helps export data from Supabase and import it into Replit's PostgreSQL database.

Usage:
  1. Export data from Supabase:
     python scripts/migrate_from_supabase.py export
     
  2. Import data into Replit PostgreSQL:
     python scripts/migrate_from_supabase.py import
     
  3. Full migration (export + import):
     python scripts/migrate_from_supabase.py migrate

Prerequisites:
  - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for export
  - DATABASE_URL must be set for import
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

EXPORT_DIR = Path("data_exports")

TABLES_TO_MIGRATE = [
    "users",
    "ideas", 
    "comments",
    "companies",
    "customers",
    "pitch_decks",
    "intellectual_properties",
    "product_requirements_documents",
    "integrations",
    "investments",
    "investment_contributions",
    "cap_table_entries",
    "user_follows",
    "idea_votes",
]


def export_from_supabase():
    """Export data from Supabase"""
    try:
        from supabase import create_client
    except ImportError:
        print("Error: supabase package not installed. Run: pip install supabase")
        return False
    
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        return False
    
    supabase = create_client(supabase_url, supabase_key)
    
    EXPORT_DIR.mkdir(exist_ok=True)
    
    export_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_subdir = EXPORT_DIR / export_timestamp
    export_subdir.mkdir(exist_ok=True)
    
    print(f"\nExporting data to: {export_subdir}")
    print("=" * 50)
    
    for table in TABLES_TO_MIGRATE:
        try:
            print(f"Exporting {table}...", end=" ")
            response = supabase.table(table).select("*").execute()
            
            if response.data:
                export_file = export_subdir / f"{table}.json"
                with open(export_file, "w") as f:
                    json.dump(response.data, f, indent=2, default=str)
                print(f"OK ({len(response.data)} rows)")
            else:
                print("Empty (0 rows)")
        except Exception as e:
            print(f"Error: {e}")
    
    print("\nExport complete!")
    print(f"Data saved to: {export_subdir}")
    return True


def import_to_replit():
    """Import data into Replit PostgreSQL"""
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print("Error: psycopg2-binary package not installed. Run: pip install psycopg2-binary")
        return False
    
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("Error: DATABASE_URL must be set")
        return False
    
    if not EXPORT_DIR.exists():
        print(f"Error: Export directory {EXPORT_DIR} not found. Run export first.")
        return False
    
    export_dirs = sorted(EXPORT_DIR.iterdir())
    if not export_dirs:
        print("Error: No exports found. Run export first.")
        return False
    
    latest_export = export_dirs[-1]
    print(f"\nImporting data from: {latest_export}")
    print("=" * 50)
    
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    for table in TABLES_TO_MIGRATE:
        export_file = latest_export / f"{table}.json"
        
        if not export_file.exists():
            print(f"Skipping {table} (no export file)")
            continue
        
        try:
            with open(export_file) as f:
                data = json.load(f)
            
            if not data:
                print(f"Skipping {table} (empty)")
                continue
            
            print(f"Importing {table}...", end=" ")
            
            columns = list(data[0].keys())
            col_str = ", ".join(f'"{c}"' for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            
            sql = f'''
                INSERT INTO "{table}" ({col_str}) 
                VALUES ({placeholders})
                ON CONFLICT DO NOTHING
            '''
            
            rows_imported = 0
            for row in data:
                values = [row.get(col) for col in columns]
                try:
                    cursor.execute(sql, values)
                    rows_imported += 1
                except Exception as e:
                    print(f"\n  Warning: Row error - {e}")
            
            conn.commit()
            print(f"OK ({rows_imported}/{len(data)} rows)")
            
        except Exception as e:
            print(f"Error: {e}")
            conn.rollback()
    
    cursor.close()
    conn.close()
    
    print("\nImport complete!")
    return True


def verify_migration():
    """Verify the migration by comparing row counts"""
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2-binary package not installed")
        return False
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL must be set")
        return False
    
    print("\nVerifying migration...")
    print("=" * 50)
    
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    for table in TABLES_TO_MIGRATE:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            count = cursor.fetchone()[0]
            print(f"{table}: {count} rows")
        except Exception as e:
            print(f"{table}: Error - {e}")
    
    cursor.close()
    conn.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="Migrate data from Supabase to Replit PostgreSQL")
    parser.add_argument("action", choices=["export", "import", "migrate", "verify"],
                        help="Action to perform")
    
    args = parser.parse_args()
    
    if args.action == "export":
        export_from_supabase()
    elif args.action == "import":
        import_to_replit()
    elif args.action == "migrate":
        if export_from_supabase():
            import_to_replit()
    elif args.action == "verify":
        verify_migration()


if __name__ == "__main__":
    main()
