import sqlite3
class DatabaseManager: 
    """ 
    Manages the SQLite database for storing application settings 
    and SKU ignore preferences. 
    """ 
    def __init__(self, db_filepath="inventory.db"): 
        self.db_filepath = db_filepath 
        self.conn = None 
        self.connect() 
        self.create_tables() 

    def connect(self): 
        """Establishes a connection to the database.""" 
        try: 
            self.conn = sqlite3.connect(self.db_filepath) 
            return True 
        except sqlite3.Error as e: 
            print(f"Database connection error: {e}") 
            return False 

    def create_tables(self): 
        """Creates the necessary tables if they don't exist.""" 
        if self.conn: 
            cursor = self.conn.cursor() 
            # Table for settings like URL and API keys 
            cursor.execute(""" 
                CREATE TABLE IF NOT EXISTS settings ( 
                    name TEXT PRIMARY KEY, 
                    value TEXT NOT NULL 
                ); 
            """) 
            # Table for the list of ignored SKUs, with separate flags for price and stock 
            cursor.execute(""" 
                CREATE TABLE IF NOT EXISTS sku_ignore_preferences ( 
                    sku TEXT PRIMARY KEY, 
                    ignore_price INTEGER NOT NULL DEFAULT 0, 
                    ignore_stock INTEGER NOT NULL DEFAULT 0 
                ); 
            """) 
            self.conn.commit() 

    def save_settings(self, settings): 
        """Saves a dictionary of settings to the database.""" 
        if self.conn: 
            cursor = self.conn.cursor() 
            for key, value in settings.items(): 
                cursor.execute(""" 
                    INSERT OR REPLACE INTO settings (name, value) VALUES (?, ?); 
                """, (key, value)) 
            self.conn.commit() 

    def load_settings(self): 
        """Loads settings from the database and returns them as a dictionary.""" 
        if self.conn: 
            cursor = self.conn.cursor() 
            cursor.execute("SELECT name, value FROM settings;") 
            settings = {row[0]: row[1] for row in cursor.fetchall()} 
            return settings 
        return {} 
    
    def save_sku_preferences(self, skus_data): 
        """Saves a list of SKU preferences (with ignore flags) to the database.""" 
        print("saving skus to db",skus_data)
        if self.conn: 
            cursor = self.conn.cursor() 
            cursor.execute("DELETE FROM sku_ignore_preferences;") 
            for sku, price_flag, stock_flag in skus_data: 
                cursor.execute(""" 
                    INSERT INTO sku_ignore_preferences (sku, ignore_price, ignore_stock) VALUES (?, ?, ?); 
                """, (sku, price_flag, stock_flag)) 
            self.conn.commit() 

    def load_sku_preferences(self): 
        """Loads SKU ignore preferences from the database.""" 
        if self.conn: 
            cursor = self.conn.cursor() 
            cursor.execute("SELECT sku, ignore_price, ignore_stock FROM sku_ignore_preferences;") 
            preferences = cursor.fetchall() 
            return preferences 
        return [] 

    def close(self): 
        """Closes the database connection.""" 
        if self.conn: 
            self.conn.close() 