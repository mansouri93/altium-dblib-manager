# -*- coding: utf-8 -*-
import unittest
from app.db.access_manager import AccessDBManager
from app.config import get_db_path

class TestPerformanceAndConnection(unittest.TestCase):
    def setUp(self):
        self.db = AccessDBManager(get_db_path())

    def tearDown(self):
        self.db.close()

    def test_persistent_connection_reuse(self):
        # 1. Initial connection
        conn1 = self.db._ensure_connection()
        self.assertIsNotNone(conn1)

        # 2. Subsequent call should reuse the same connection instance
        conn2 = self.db._ensure_connection()
        self.assertIs(conn1, conn2)

        # 3. get_connection context manager must use the persistent connection
        with self.db.get_connection() as c:
            self.assertIs(c, conn1)

    def test_columns_and_schema_caching(self):
        # 1. First call populates cache
        cols1 = self.db.get_columns("Capacitor")
        self.assertIn("Capacitor", self.db._columns_cache)

        # 2. Cached call returns identical columns
        cols2 = self.db.get_columns("Capacitor")
        self.assertEqual(cols1, cols2)

        # 3. Invalidate cache
        self.db.invalidate_caches("Capacitor")
        self.assertNotIn("Capacitor", self.db._columns_cache)

    def test_clean_close(self):
        self.db._ensure_connection()
        self.assertIsNotNone(self.db._conn)
        self.db.close()
        self.assertIsNone(self.db._conn)
        self.assertEqual(len(self.db._columns_cache), 0)

if __name__ == "__main__":
    unittest.main()
