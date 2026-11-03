import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "govcon_bbd"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

def test_connection():
    if not DB_CONFIG["password"]:
        print("Database password is missing from the .env file.")
        return

    try:
        with psycopg2.connect(**DB_CONFIG) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), current_user, version();"
                )
                database, user, version = cursor.fetchone()

                print("SUCCESS: Python is connected to PostgreSQL!")
                print(f"Database: {database}")
                print(f"User: {user}")
                print(f"PostgreSQL: {version.split(',')[0]}")

    except psycopg2.Error as error:
        print("Database connection failed.")
        print(f"Error: {error}")

if __name__ == "__main__":
    test_connection()