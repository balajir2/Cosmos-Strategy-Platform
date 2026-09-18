import database


def test_get_db_connection_reuses_returned_connection():
    conn1 = database.get_db_connection()
    fd1 = conn1.fileno()
    conn1.close()

    conn2 = database.get_db_connection()
    try:
        # Same physical socket reused, not a fresh psycopg2.connect() each time.
        # get_db_connection() returns a fresh wrapper object every call, so
        # comparing the underlying OS file descriptor - not Python identity -
        # is what actually proves reuse.
        assert conn2.fileno() == fd1
    finally:
        conn2.close()


def test_reused_connection_still_executes_queries():
    conn1 = database.get_db_connection()
    conn1.close()

    conn2 = database.get_db_connection()
    try:
        cursor = conn2.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
        cursor.close()
    finally:
        conn2.close()


def test_get_db_connection_registers_vector_adapter():
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT '[1,2,3]'::vector")
        value = cursor.fetchone()[0]
        # pgvector's registered adapter returns a Vector wrapper, not a raw string
        assert value.to_list() == [1.0, 2.0, 3.0]
        cursor.close()
    finally:
        conn.close()


def test_concurrent_connections_are_distinct_until_returned():
    conn1 = database.get_db_connection()
    conn2 = database.get_db_connection()
    try:
        assert conn1.fileno() != conn2.fileno()
    finally:
        conn1.close()
        conn2.close()
