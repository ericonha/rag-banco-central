#!/usr/bin/env python3
"""Check database schema."""

import psycopg

conn_string = "postgresql://postgresml:postgresml@localhost:5433/postgresml"

try:
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            # List all tables
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = cur.fetchall()
            print("Tables in database:")
            for table in tables:
                print(f"  - {table[0]}")
            
            print("\n" + "="*60)
            print("Documents table columns:")
            print("="*60)
            
            if any('documents' in str(t) for t in tables):
                cur.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'documents'
                    ORDER BY ordinal_position
                """)
                for col_name, data_type, nullable in cur.fetchall():
                    print(f"  {col_name:20s} {data_type:20s} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
            else:
                print("  ERROR: documents table not found!")
                
except Exception as e:
    print(f"Connection error: {e}")
    print("\nMake sure Docker is running and database is initialized")
