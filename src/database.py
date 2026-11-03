"""
GovCon BD Intelligence & Automation Platform
Module: PostgreSQL Database Connection
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def get_database_config():
    """Read PostgreSQL configuration from the project .env file."""

    required_variables = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]

    missing_variables = [
        variable
        for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing_variables:
        raise RuntimeError(
            "Missing database configuration variables: "
            + ", ".join(missing_variables)
            + ". Check your .env file."
        )

    return {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT")),
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "connect_timeout": 10,
        "application_name": "GovCon_BD_Intelligence_Platform",
    }


@contextmanager
def get_connection():
    """Open a PostgreSQL connection and close it automatically."""

    connection = None

    try:
        connection = psycopg2.connect(**get_database_config())
        yield connection
    finally:
        if connection is not None:
            connection.close()


def test_connection():
    """Return database connection information."""

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    version();
                """
            )

            database_name, database_user, database_version = cursor.fetchone()

    return {
        "database": database_name,
        "user": database_user,
        "version": database_version,
    }


def fetch_all(query, params=None):
    """Execute a SELECT query and return all rows as dictionaries."""

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


def fetch_one(query, params=None):
    """Execute a SELECT query and return one row, or None."""

    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row is not None else None


def execute_query(query, params=None):
    """Execute an INSERT, UPDATE, or DELETE and commit the transaction."""

    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                affected_rows = cursor.rowcount

            connection.commit()
            return affected_rows

        except Exception:
            connection.rollback()
            raise