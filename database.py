import sqlite3

DATABASE_NAME = 'ignored_products.db'

def setup_database():
    """Creates the database and the table for ignored products."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ignored_items (
            sku TEXT PRIMARY KEY,
            ignore_price INTEGER,
            ignore_stock INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def add_ignored_product(sku, ignore_price=False, ignore_stock=False):
    """Adds or updates a product in the ignore list."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO ignored_items (sku, ignore_price, ignore_stock)
        VALUES (?, ?, ?)
    ''', (sku, int(ignore_price), int(ignore_stock)))
    conn.commit()
    conn.close()

def get_ignored_products():
    """Retrieves all ignored products from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT sku, ignore_price, ignore_stock FROM ignored_items')
    ignored_list = {row[0]: {'price': bool(row[1]), 'stock': bool(row[2])} for row in cursor.fetchall()}
    conn.close()
    return ignored_list

def remove_ignored_product(sku):
    """Removes a product from the ignore list."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ignored_items WHERE sku = ?', (sku,))
    conn.commit()
    conn.close()