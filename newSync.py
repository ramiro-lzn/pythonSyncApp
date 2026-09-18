import tkinter as tk 
from tkinter import filedialog, messagebox, scrolledtext 
import csv 
import os 
import sys 
import json 
import sqlite3 
from woocommerce import API 
import threading 
import queue 

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

class App:

    def __init__(self, root): 
        self.root = root
        self.root.title("Inventory Sync Application")
        self.root.geometry("800x600")
        self.root.configure(bg="#f0f0f0")
        self.db = DatabaseManager()
        self.log_queue = queue.Queue()
        self.csv_filepath = None
        self.wc_product_cache = None 

        #Main frame with some padding
        main_frame = tk.Frame(root, padx=20, pady=20, bg="#F3F4F6") 
        main_frame.pack(fill=tk.BOTH, expand=True) 

        # Credentials and File section 
        credentials_frame = tk.LabelFrame(main_frame, text="Credentials & File", padx=10, pady=10, bg="#E5E7EB", font=("Arial", 10, "bold")) 
        credentials_frame.pack(fill=tk.X, pady=10) 

        # Store URL
        tk.Label(credentials_frame, text="Store URL:", bg="#E5E7EB").grid(row=0, column=0, sticky="w", padx=5, pady=2) 
        self.store_url_entry = tk.Entry(credentials_frame, width=50) 
        self.store_url_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

        # Consumer Key 
        tk.Label(credentials_frame, text="Consumer Key:", bg="#E5E7EB").grid(row=1, column=0, sticky="w", padx=5, pady=2) 
        self.consumer_key_entry = tk.Entry(credentials_frame, width=50) 
        self.consumer_key_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew") 

        # Consumer Secret 
        tk.Label(credentials_frame, text="Consumer Secret:", bg="#E5E7EB").grid(row=2, column=0, sticky="w", padx=5, pady=2) 
        self.consumer_secret_entry = tk.Entry(credentials_frame, width=50, show="*") 
        self.consumer_secret_entry.grid(row=2, column=1, padx=5, pady=2, sticky="ew") 

        # CSV File 
        tk.Label(credentials_frame, text="CSV File:", bg="#E5E7EB").grid(row=3, column=0, sticky="w", padx=5, pady=2) 
        self.csv_path_label = tk.Label(credentials_frame, text="No file selected", anchor="w", fg="gray", bg="#E5E7EB") 
        self.csv_path_label.grid(row=3, column=1, sticky="ew", padx=5, pady=2) 
        tk.Button(credentials_frame, text="Browse...", command=self.browse_csv).grid(row=3, column=2, padx=5, pady=2) 

    def browse_csv(self): 
        """ 
        Opens a file dialog to select the CSV file. 
        """ 
        self.csv_filepath = filedialog.askopenfilename( 
            defaultextension=".csv", 
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")] 
        ) 
        if self.csv_filepath: 
            self.csv_path_label.config(text=os.path.basename(self.csv_filepath), fg="black") 
            self.log(f"Selected CSV file: {self.csv_filepath}") 
        else: 
            self.csv_path_label.config(text="No file selected", fg="gray") 
            self.log("File selection cancelled.") 

    def log(self, message): 
        """ 
        Thread-safe method to update the log text widget. 
        """ 
        self.log_text.config(state=tk.NORMAL) 
        self.log_text.insert(tk.END, message + "\n") 
        self.log_text.config(state=tk.DISABLED) 
        self.log_text.see(tk.END) 

if __name__ == "__main__": 
    
    # Set up the main GUI window 
    root = tk.Tk() 
    app = App(root) 
    root.mainloop()