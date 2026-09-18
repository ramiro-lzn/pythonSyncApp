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

class WooCommerceInventoryChecker: 
    """ 
    A class to handle checking a WooCommerce store's product inventory 
    against a local CSV file to find products that are not present in the CSV. 
    """ 

    def __init__(self, store_url, consumer_key, consumer_secret, log_queue): 
        """ 
        Initializes the WooCommerce API client. 

        Args: 
            store_url (str): The URL of your WooCommerce store. 
            consumer_key (str): The consumer key for the WooCommerce REST API. 
            consumer_secret (str): The consumer secret for the WooCommerce REST API. 
            log_queue (queue.Queue): A queue for thread-safe logging. 
        """ 
        self.store_url = store_url 
        self.consumer_key = consumer_key 
        self.consumer_secret = consumer_secret 
        self.log_queue = log_queue 
        self.wcapi = API( 
            url=store_url, 
            consumer_key=consumer_key, 
            consumer_secret=consumer_secret, 
            version="wc/v3", 
            timeout=30, 
            verify_ssl=True 
        ) 

    def _log(self, message): 
        """ 
        Puts a message in the log queue for the GUI thread to display. 
        """ 
        self.log_queue.put(message) 

    def get_all_products(self): 
        """ 
        Retrieves all products from the WooCommerce store, handling pagination. 
        """ 
        all_products = [] 
        page = 1 
        per_page = 100 
        while True: 
            try: 
                self._log(f"Retrieving products from page {page}...") 
                response = self.wcapi.get("products", params={"page": page, "per_page": per_page, "status": "any"}) 
                
                if response.status_code not in [200, 201]: 
                    self._log(f"Error: API returned status code {response.status_code}.") 
                    self._log(f"Response text: {response.text}") 
                    return None 

                products = response.json() 
                if not products: 
                    break 
                
                all_products.extend(products) 
                page += 1 
                
            except Exception as e: 
                self._log(f"Error retrieving products from page {page}: {e}") 
                return None 
        
        return all_products 
    
    def _read_csv(self, csv_filepath): 
        """ 
        Reads product data from a CSV file. 
        """ 
        try: 
            with open(csv_filepath, mode='r', encoding='utf-8') as file: 
                reader = csv.DictReader(file) 
                if 'Item Code' not in reader.fieldnames or 'Price' not in reader.fieldnames or 'On Hand' not in reader.fieldnames: 
                    self._log("Error: CSV file must contain columns 'Item Code', 'Price', and 'On Hand'.") 
                    return None 
                
                csv_data = {} 
                for row in reader: 
                    item_code = row.get('Item Code') 
                    if item_code: 
                        csv_data[item_code.strip()] = row 
                return csv_data 
        except Exception as e: 
            self._log(f"Error reading CSV file: {e}") 
            return None 

    def find_missing_in_csv(self, csv_filepath, skus_to_ignore, wc_product_cache): 
        """ 
        Compares WooCommerce products against a CSV file to find products 
        that are not listed in the CSV. This is run in a separate thread. 
        """ 
        if not os.path.exists(csv_filepath): 
            self._log(f"Error: The file '{csv_filepath}' was not found.") 
            return 
        
        if not wc_product_cache:
            self._log("Product cache is empty. Please load products first.")
            return

        self._log("Step 1: Reading product IDs from CSV file...") 
        csv_product_ids = set() 
        skipped_count = 0 
        try: 
            with open(csv_filepath, mode='r', encoding='utf-8') as file: 
                reader = csv.DictReader(file) 
                if 'Item Code' not in reader.fieldnames: 
                    self._log("Error: CSV file must contain a column named 'Item Code'.") 
                    return 
                
                for row in reader: 
                    item_code = row.get('Item Code') 
                    if item_code: 
                        csv_product_ids.add(item_code.strip()) 
                    else: 
                        skipped_count += 1 
        except Exception as e: 
            self._log(f"Error reading CSV file: {e}") 
            return 
        
        self._log(f"Found {len(csv_product_ids)} unique product IDs in the CSV file.") 
        if skipped_count > 0: 
            self._log(f"Skipped {skipped_count} rows due to missing 'Item Code'.") 

        self._log(f"Using cached product data for comparison.") 

        self._log("\nStep 2: Comparing datasets and identifying missing products...") 
        missing_products = [] 
        all_wc_products = list(wc_product_cache.values())
        for product in all_wc_products: 
            sku = product.get('sku') 
            if sku and sku not in csv_product_ids and sku not in skus_to_ignore: 
                missing_products.append(product) 

        self._log("\n--- Summary ---") 
        if missing_products: 
            self._log(f"Found {len(missing_products)} WooCommerce products NOT in the CSV:") 
            for product in missing_products: 
                self._log(f"- ID: {product.get('id')}, Name: '{product.get('name')}', SKU: '{product.get('sku')}'") 
        else: 
            self._log("All products in the store were found in your CSV file.") 
        self._log("\nProcess complete.") 

    def bulk_update_with_user_input(self, csv_filepath, update_candidates):
        """
        Performs the bulk update after the user has confirmed.
        """
        final_update_payload = []
    
        if not update_candidates:
            self._log("\nNo products selected for update. Exiting.")
            return

        for product in update_candidates:
            data = {
                'id': product['wc_product_id']
            }

            if 'new_price' in product:
                data['regular_price'] = str(product['new_price'])
            if 'new_stock' in product:
                data['manage_stock'] = True
                data['stock_quantity'] = product['new_stock']
            final_update_payload.append(data)

        # --- Start of fix for 413 error ---
        batch_size = 100  # WooCommerce API limit
        chunks = [final_update_payload[i:i + batch_size] for i in range(0, len(final_update_payload), batch_size)]

        self._log(f"\nStep 7: Preparing to update {len(final_update_payload)} products in {len(chunks)} batches...")

        total_updated = 0
        total_failed = 0
        for i, chunk in enumerate(chunks):
            self._log(f"Sending batch {i+1} of {len(chunks)}...")
            try:
                response = self.wcapi.post("products/batch", {"update": chunk})
                if response.status_code in [200, 201]:
                    updated_products = response.json().get('update', [])
                    failed_products = response.json().get('errors', [])
                
                    total_updated += len(updated_products)
                    total_failed += len(failed_products)
                
                    if failed_products:
                        self._log(f"  Batch {i+1} had {len(failed_products)} failures.")
                        for error in failed_products:
                            self._log(f"  - Error on product ID {error.get('id')}: {error.get('message')}")
                else:
                    self._log(f"  Batch {i+1} failed. Status code: {response.status_code}, Response: {response.text}")
                    break
            except Exception as e:
                self._log(f"An unexpected error occurred during batch {i+1}: {e}")
                break
            
        self._log("\n--- Update Results ---")
        self._log(f"Successfully updated: {total_updated} products.")
        if total_failed > 0:
            self._log(f"Total failed to update: {total_failed} products.")
    
        self._log("\nUpdate complete.")
        # --- End of fix ---

class App: 
    """ 
    The main GUI application class. 
    """ 
    def __init__(self, root): 
        self.root = root 
        self.root.title("WooCommerce Inventory Manager") 
        self.root.geometry("800x900") 
        self.root.configure(bg="#F3F4F6") 

        self.db = DatabaseManager() 
        self.log_queue = queue.Queue() 
        self.csv_filepath = None 
        self.wc_product_cache = None 

        # Main frame with some padding 
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
        
        credentials_frame.grid_columnconfigure(1, weight=1) 

        # SKU Ignore Preferences section 
        ignore_frame = tk.LabelFrame(main_frame, text="SKU Ignore Preferences", padx=10, pady=10, bg="#E5E7EB", font=("Arial", 10, "bold")) 
        ignore_frame.pack(fill=tk.X, pady=10) 

        # SKU Input 
        tk.Label(ignore_frame, text="SKU:", bg="#E5E7EB").grid(row=0, column=0, sticky="w", padx=5, pady=2) 
        self.sku_to_ignore_entry = tk.Entry(ignore_frame, width=20) 
        self.sku_to_ignore_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew") 

        # Checkboxes for preferences 
        self.ignore_price_var = tk.IntVar() 
        self.ignore_stock_var = tk.IntVar() 
        tk.Checkbutton(ignore_frame, text="Ignore Price", variable=self.ignore_price_var, bg="#E5E7EB").grid(row=0, column=2, padx=5, pady=2, sticky="w") 
        tk.Checkbutton(ignore_frame, text="Ignore Stock", variable=self.ignore_stock_var, bg="#E5E7EB").grid(row=0, column=3, padx=5, pady=2, sticky="w") 

        # Buttons 
        tk.Button(ignore_frame, text="Add SKU", command=self.add_sku_preference, bg="#10B981", fg="white", activebackground="#059669").grid(row=0, column=4, padx=5, pady=2) 
        tk.Button(ignore_frame, text="Select from Store", command=self.run_sku_selector_dialog, bg="#3B82F6", fg="white", activebackground="#2563EB").grid(row=0, column=5, padx=5, pady=2)

        # Listbox to display current preferences 
        self.preferences_listbox = tk.Listbox(ignore_frame, height=10, selectmode=tk.MULTIPLE) 
        self.preferences_listbox.grid(row=1, column=0, columnspan=6, padx=5, pady=5, sticky="ew") 

        tk.Button(ignore_frame, text="Remove Selected", command=self.remove_sku_preference, bg="#EF4444", fg="white", activebackground="#DC2626").grid(row=2, column=0, columnspan=6, pady=5) 
        
        ignore_frame.grid_columnconfigure(1, weight=1) 

        # Action Buttons section 
        button_frame = tk.Frame(main_frame, bg="#F3F4F6") 
        button_frame.pack(pady=10) 
        
        tk.Button(button_frame, text="Save Credentials", command=self.save_credentials, 
                    bg="#9CA3AF", fg="white", activebackground="#6B7280", relief=tk.RAISED, 
                    bd=3, padx=10).pack(side=tk.LEFT, padx=10) 
        
        tk.Button(button_frame, text="Load Products from Store", command=self.run_product_load,
                  bg="#4F46E5", fg="white", activebackground="#3730A3", relief=tk.RAISED,
                  bd=3, padx=10).pack(side=tk.LEFT, padx=10)

        tk.Button(button_frame, text="Check for Missing Products", command=self.run_missing_check, 
                    bg="#10B981", fg="white", activebackground="#059669", relief=tk.RAISED, 
                    bd=3, padx=10).pack(side=tk.LEFT, padx=10) 
        
        tk.Button(button_frame, text="Bulk Update Inventory", command=self.run_bulk_update, 
                    bg="#3B82F6", fg="white", activebackground="#2563EB", relief=tk.RAISED, 
                    bd=3, padx=10).pack(side=tk.LEFT, padx=10) 

        # Log section 
        log_frame = tk.LabelFrame(main_frame, text="Activity Log", padx=10, pady=10, bg="#F3F4F6", font=("Arial", 10, "bold")) 
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10) 
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#1F2937", fg="#E5E7EB") 
        self.log_text.pack(fill=tk.BOTH, expand=True) 

        self.root.after(100, self.process_log_queue) 
        self.load_config() 

    def load_config(self): 
        """ 
        Loads credentials and ignored SKUs from the database. 
        """ 
        settings = self.db.load_settings() 
        self.store_url_entry.delete(0, tk.END) 
        self.store_url_entry.insert(0, settings.get("store_url", "")) 
        self.consumer_key_entry.delete(0, tk.END) 
        self.consumer_key_entry.insert(0, settings.get("consumer_key", "")) 
        self.consumer_secret_entry.delete(0, tk.END) 
        self.consumer_secret_entry.insert(0, settings.get("consumer_secret", "")) 
        
        self.preferences = self.db.load_sku_preferences() 
        self.update_preferences_listbox() 
        
        self.log("Configuration loaded from database.") 

    def save_credentials(self): 
        """ 
        Saves credentials and ignored SKUs to the database. 
        """ 
        settings = { 
            "store_url": self.store_url_entry.get(), 
            "consumer_key": self.consumer_key_entry.get(), 
            "consumer_secret": self.consumer_secret_entry.get() 
        } 
        self.db.save_settings(settings) 
        #self.db.save_sku_preferences(self.preferences) 
        
        self.log("Credentials saved to database.") 
        messagebox.showinfo("Success", "Credentials saving preferences to db")

    def add_sku_preference(self): 
        """Adds a new SKU and its preferences to the list.""" 
        sku = self.sku_to_ignore_entry.get().strip() 
        if not sku: 
            messagebox.showerror("Error", "Please enter an SKU to add.") 
            return 

        # Check if product data is loaded and if the SKU exists in the cache
        if not self.wc_product_cache or sku not in self.wc_product_cache:
            messagebox.showerror("Error", "Product data not loaded or SKU not found in store.")
            return

        ignore_price = self.ignore_price_var.get() 
        ignore_stock = self.ignore_stock_var.get() 

        if not ignore_price and not ignore_stock: 
            messagebox.showerror("Error", "Please select at least one option to ignore (Price or Stock).") 
            return 
        
        # Check if SKU already exists and update it 
        found = False 
        for i, (s, p, st) in enumerate(self.preferences): 
            if s == sku: 
                self.preferences[i] = (sku, ignore_price, ignore_stock) 
                found = True 
                break 
        
        if not found: 
            self.preferences.append((sku, ignore_price, ignore_stock)) 
        #saving preferences to db
        self.db.save_sku_preferences(self.preferences) 

        self.update_preferences_listbox() 
        self.sku_to_ignore_entry.delete(0, tk.END) 
        self.ignore_price_var.set(0) 
        self.ignore_stock_var.set(0) 

    def remove_sku_preference(self): 
        """Removes the selected SKU preference(s) from the list.""" 
        selected_indices = self.preferences_listbox.curselection()
        
        if not selected_indices:
            messagebox.showerror("Error", "Please select one or more SKUs to remove.")
            return

        # Delete indices in reverse order to keep the remaining indices valid
        for index in reversed(selected_indices):
            try:
                del self.preferences[index]
            except IndexError:
                # Should not happen if curselection() is used correctly, but good for robustness
                self.log(f"Warning: Could not remove preference at index {index}. It may no longer exist.")

        self.update_preferences_listbox() 
        self.db.save_sku_preferences(self.preferences) # Save updated preferences to database
    def update_preferences_listbox(self): 
        """Updates the listbox with the current SKU preferences.""" 
        self.preferences_listbox.delete(0, tk.END) 
        for sku, ignore_price, ignore_stock in self.preferences: 
            price_status = "P" if ignore_price else "" 
            stock_status = "S" if ignore_stock else "" 
            status = f"({price_status},{stock_status})" if price_status or stock_status else "" 

            # Conditionally get the product title from the cache
            title = ""
            if self.wc_product_cache and sku in self.wc_product_cache:
                product = self.wc_product_cache.get(sku, {})
                title = product.get('name', 'N/A')
            
            # Form the display text based on whether a title was found
            if title:
                display_text = f"{sku} - {title} {status}"
            else:
                display_text = f"{sku} {status}"

            self.preferences_listbox.insert(tk.END, display_text)

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

    def process_log_queue(self): 
        """ 
        Processes messages from the log queue in the main thread. 
        """ 
        while not self.log_queue.empty(): 
            message = self.log_queue.get_nowait() 
            self.log(message) 
        self.root.after(100, self.process_log_queue) 

    def get_credentials(self): 
        """ 
        Retrieves credentials from the input fields. 
        """ 
        store_url = self.store_url_entry.get().strip() 
        consumer_key = self.consumer_key_entry.get().strip() 
        consumer_secret = self.consumer_secret_entry.get().strip() 
        return store_url, consumer_key, consumer_secret 

    def run_product_load(self):
        """
        Starts the process of fetching all products from the store.
        """
        store_url, consumer_key, consumer_secret = self.get_credentials()
        if not all([store_url, consumer_key, consumer_secret]):
            messagebox.showerror("Error", "Please fill in all credentials.")
            return

        self.log_text.delete(1.0, tk.END)
        self.log("Fetching all products from store...")
        
        self.product_queue = queue.Queue()
        checker = WooCommerceInventoryChecker(store_url, consumer_key, consumer_secret, self.log_queue)
        thread = threading.Thread(target=self._load_products_thread, args=(checker, self.product_queue))
        thread.daemon = True
        thread.start()
        self.root.after(100, self.check_product_queue)
    
    def _load_products_thread(self, checker, q):
        """Worker thread to load products and put them into a queue."""
        products = checker.get_all_products()
        if products:
            product_dict = {p['sku']: p for p in products if 'sku' in p and p['sku']}
            q.put(product_dict)
        else:
            q.put(None)
    
    def check_product_queue(self):
        """
        Checks the product queue for results from the background thread.
        """
        try:
            products = self.product_queue.get_nowait()
            if products is not None:
                self.wc_product_cache = products
                self.log(f"Successfully cached {len(self.wc_product_cache)} products from the store.")
                self.update_preferences_listbox() # <<-- ADDED THIS LINE
            else:
                self.log("Failed to load products.")
        except queue.Empty:
            self.root.after(100, self.check_product_queue)

    def run_sku_selector_dialog(self):
        """
        Displays a separate window to select SKUs to ignore.
        """
        if not self.wc_product_cache:
            messagebox.showerror("Error", "No products loaded. Please click 'Load Products from Store' first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Select Products to Ignore")
        dialog.geometry("600x600")
        
        tk.Label(dialog, text="Select products to ignore price and/or stock updates for:", font=("", 12)).pack(pady=10)

        # Create a frame for the listbox and checkboxes
        selection_frame = tk.Frame(dialog)
        selection_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(selection_frame)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(selection_frame, orient="vertical", command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create a frame inside the canvas to hold the product list
        inner_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # Variables to hold the state of checkboxes
        self.checkbox_vars = {}

        # Populate the inner frame with products and checkboxes
        sorted_skus = sorted(self.wc_product_cache.keys())
        for sku in sorted_skus:
            product = self.wc_product_cache[sku]
            
            product_frame = tk.Frame(inner_frame)
            product_frame.pack(fill=tk.X, pady=2)
            
            # Check for existing ignore preferences
            current_pref = next(((s, p, st) for s, p, st in self.preferences if s == sku), None)

            ignore_price_var = tk.IntVar(value=current_pref[1] if current_pref else 0)
            ignore_stock_var = tk.IntVar(value=current_pref[2] if current_pref else 0)

            tk.Label(product_frame, text=f"{sku} - {product.get('name', 'N/A')}").pack(side=tk.LEFT, padx=5)
            tk.Checkbutton(product_frame, text="Ignore Price", variable=ignore_price_var).pack(side=tk.RIGHT, padx=5)
            tk.Checkbutton(product_frame, text="Ignore Stock", variable=ignore_stock_var).pack(side=tk.RIGHT, padx=5)

            self.checkbox_vars[sku] = (ignore_price_var, ignore_stock_var)

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", on_frame_configure)
        
        # Confirmation button
        def on_confirm():
            new_preferences = []
            for sku, (price_var, stock_var) in self.checkbox_vars.items():
                if price_var.get() or stock_var.get():
                    new_preferences.append((sku, price_var.get(), stock_var.get()))
            
            # Update existing preferences or add new ones
            for sku, price_flag, stock_flag in new_preferences:
                found = False
                for i, (s, p, st) in enumerate(self.preferences):
                    if s == sku:
                        self.preferences[i] = (sku, price_flag, stock_flag)
                        found = True
                        break
                if not found:
                    self.preferences.append((sku, price_flag, stock_flag))

            # Remove preferences that were unchecked
            current_skus = {pref[0] for pref in self.preferences}
            selected_skus = {pref[0] for pref in new_preferences}
            skus_to_remove = current_skus - selected_skus
            self.preferences = [pref for pref in self.preferences if pref[0] not in skus_to_remove]
            
            self.update_preferences_listbox()
            self.db.save_sku_preferences(self.preferences) # Save preferences to database
            #self.save_config() # Save changes to database
            dialog.destroy()
            messagebox.showinfo("Success", "SKU preferences updated!")

        tk.Button(dialog, text="Save Preferences", command=on_confirm, padx=10, pady=5).pack(pady=10)


    def run_missing_check(self): 
        """ 
        Starts the find_missing_in_csv operation in a new thread. 
        """ 
        store_url, consumer_key, consumer_secret = self.get_credentials() 
        skus_to_ignore = [sku for sku, _, _ in self.preferences] 

        if not all([store_url, consumer_key, consumer_secret, self.csv_filepath]): 
            messagebox.showerror("Error", "Please fill in all credentials and select a CSV file.") 
            return 
        
        if not self.wc_product_cache:
            messagebox.showerror("Error", "Please load products from the store first.")
            return

        self.log_text.delete(1.0, tk.END) 
        self.log("Starting 'Check for Missing Products'...") 

        checker = WooCommerceInventoryChecker(store_url, consumer_key, consumer_secret, self.log_queue) 
        thread = threading.Thread(target=checker.find_missing_in_csv, args=(self.csv_filepath, set(skus_to_ignore), self.wc_product_cache)) 
        thread.daemon = True 
        thread.start() 

    def run_bulk_update(self): 
        """ 
        Starts the bulk update operation by first finding candidates, then 
        prompting the user for exclusion, and finally performing the update. 
        """ 
        store_url, consumer_key, consumer_secret = self.get_credentials() 

        if not all([store_url, consumer_key, consumer_secret, self.csv_filepath]): 
            messagebox.showerror("Error", "Please fill in all credentials and select a CSV file.") 
            return 

        if not self.wc_product_cache:
            messagebox.showerror("Error", "Please load products from the store first.")
            return

        self.log_text.delete(1.0, tk.END) 
        self.log("Starting 'Bulk Update Inventory'...") 

        checker = WooCommerceInventoryChecker(store_url, consumer_key, consumer_secret, self.log_queue) 
        
        # Create a dictionary for quick lookup of ignore preferences 
        ignore_preferences = {sku: {'price': bool(price_flag), 'stock': bool(stock_flag)} for sku, price_flag, stock_flag in self.preferences} 

        # This part of the logic needs to run in a thread to not freeze the GUI 
        def find_candidates_and_prompt(): 
            csv_data = checker._read_csv(self.csv_filepath) 
            all_wc_products = list(self.wc_product_cache.values())

            if not csv_data: 
                return 

            update_candidates = [] 
            checker._log("\nStep 3: Comparing data and identifying update candidates...") 
            for wc_product in all_wc_products: 
                sku = wc_product.get('sku') 
                
                if sku and sku in csv_data: 
                    csv_product = csv_data[sku] 
                    print(csv_product)
                    wc_price_str = wc_product.get('regular_price', '0')
                    if wc_price_str == "":
                        checker._log(f"⚠️ Warning: Skipping SKU '{sku}' ('{wc_product.get('name', 'N/A')}') because its WooCommerce price is an empty string ('').")
                        continue # Skip to the next product
                    
                    try:
                        wc_price = float(wc_price_str)
                    except ValueError:
                        checker._log(f"❌ Error: Skipping SKU '{sku}' due to invalid price format: '{wc_price_str}'.")
                        continue # Skip to the next product 
                    # 1. Safely retrieve the price value, default to 0 if the key ('Price') is missing.
                    price_value_raw = csv_product.get('Price', 0)

                    # 2. Convert to string and strip whitespace, then check if it's an empty string.
                    #    This handles: missing key (returns 0), empty cell (''), and whitespace ('   ').
                    if isinstance(price_value_raw, str):
                        price_value_raw = price_value_raw.strip()
                    try:
                        # 3. Attempt conversion. This is the only place a non-numeric string (like "A" or "N/A") will fail.
                        csv_price = float(price_value_raw)

                    except ValueError as e:
                        # 4. Handle conversion failure (e.g., "A", "N/A", "FREE").
                        checker._log(f"❌ Error: Skipping SKU '{sku}' due to invalid CSV Price: '{price_value_raw}'. (Error: {e})")
                        # You must skip this product by returning from the loop or setting the price to a safe value.
                        # The simplest action is to skip the product entirely for this update.
                        continue
                    wc_stock = int(wc_product.get('stock_quantity', 0) if wc_product.get('stock_quantity') is not None else 0) 

                    # 1. Safely retrieve the raw stock value, defaulting to 0 if the key is missing.
                    stock_value_raw = csv_product.get('On Hand', 0)

                    # 2. Clean and handle empty/whitespace strings.
                    if isinstance(stock_value_raw, str):
                        stock_value_raw = stock_value_raw.strip()
                        # Treat an empty string (or one containing only spaces) as zero
                        if stock_value_raw == "":
                            stock_value_raw = 0

                    try:
                        # 3. Attempt robust conversion: float() handles numbers/strings, then int() truncates.
                        #    This step will fail if the string is non-numeric (e.g., "A", "N/A").
                        csv_stock_full = int(float(stock_value_raw))
    
                        # 4. Apply the adjustment (accounting for opened bottles)
                        csv_stock = csv_stock_full - 1
    
                        # Ensure stock is not negative after adjustment
                        if csv_stock < 0:
                            csv_stock = 0

                    except ValueError:
                        # 5. Handle any conversion error (e.g., non-numeric string like "FREE")
                        checker._log(f"❌ Error: Skipping SKU '{sku}' due to invalid CSV 'On Hand' value: '{stock_value_raw}'. Must be a number.")
                        # Use 'continue' if this logic is inside a loop over CSV products.
                        # If not inside a loop, you would return a default value or raise a custom error.
                        # Assuming this is inside the product iteration loop:
                        continue 

                    # Use csv_stock for further comparison/update logic
                    # Check ignore preferences for this specific SKU 
                    ignore_price = ignore_preferences.get(sku, {}).get('price', False) 
                    ignore_stock = ignore_preferences.get(sku, {}).get('stock', False) 

                    price_changed = wc_price != csv_price and not ignore_price 
                    stock_changed = wc_stock != csv_stock and not ignore_stock 

                    if price_changed or stock_changed: 
                        candidate_data = { 
                            'wc_product_id': wc_product['id'], 
                            'sku': sku, 
                            'name': wc_product.get('name', 'N/A') 
                        } 
                        if price_changed:
                            candidate_data['current_price'] = wc_price
                            candidate_data['new_price'] = csv_price 
                        if stock_changed: 
                            candidate_data['current_stock'] = wc_stock
                            candidate_data['new_stock'] = csv_stock 
                        
                        update_candidates.append(candidate_data) 
            
            if not update_candidates: 
                checker._log("\nNo products require an update based on your CSV data and ignore preferences.") 
                return 

            self.root.after(0, lambda: self.show_update_dialog(update_candidates)) 

        thread = threading.Thread(target=find_candidates_and_prompt) 
        thread.daemon = True 
        thread.start() 

    def show_update_dialog(self, update_candidates):
        """
        Displays a separate window for the user to review and exclude products,
        with options to ignore price/stock and save these preferences.

        Titles are limited in length for layout reasons; hovering will show the
        full SKU/name text if it was shortened.
        """
        # helper utilities used only in this dialog
        def _truncate(text, max_len=50):
            if len(text) <= max_len:
                return text
            return text[: max_len - 3] + "..."

        class ToolTip:
            """Basic tooltip widget for Tkinter controls."""
            def __init__(self, widget, text):
                self.widget = widget
                self.text = text
                self.tipwindow = None
                widget.bind("<Enter>", self.show)
                widget.bind("<Leave>", self.hide)

            def show(self, event=None):
                if self.tipwindow or not self.text:
                    return
                x = self.widget.winfo_rootx() + 20
                y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
                self.tipwindow = tw = tk.Toplevel(self.widget)
                tw.wm_overrideredirect(1)
                tw.wm_geometry(f"+{x}+{y}")
                label = tk.Label(
                    tw,
                    text=self.text,
                    justify=tk.LEFT,
                    background="#ffffe0",
                    relief=tk.SOLID,
                    borderwidth=1,
                    font=("tahoma", "8", "normal"),
                )
                label.pack(ipadx=1)

            def hide(self, event=None):
                tw = self.tipwindow
                self.tipwindow = None
                if tw:
                    tw.destroy()

        dialog = tk.Toplevel(self.root)
        dialog.title("Review Products for Update")
        dialog.geometry("800x800")

        # --- Search Functionality ---
        search_frame = tk.Frame(dialog)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        tk.Label(search_frame, text="Search SKU or Name:").pack(side=tk.LEFT, padx=(0, 5))
        search_entry = tk.Entry(search_frame)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def filter_products():
            query = search_entry.get().lower()
            found_match = False
            for product_sku, product_frame in self.product_frames.items():
                product_info = self.wc_product_cache.get(product_sku, {})
                sku = product_info.get('sku', '').lower()
                name = product_info.get('name', '').lower()

                if query in sku or query in name:
                    product_frame.pack(fill=tk.X, padx=5, pady=2)
                    found_match = True
                else:
                    product_frame.pack_forget()

            if not found_match and query:
                no_results_label.pack(fill=tk.X, pady=10)
            else:
                no_results_label.pack_forget()

            # Update canvas scroll region after packing/unpacking widgets
            # The fix is to ensure this line is called, even if the filter doesn't change things.
            dialog.after(100, lambda: canvas.configure(scrollregion=canvas.bbox("all")))

        tk.Button(search_frame, text="Search", command=filter_products).pack(side=tk.LEFT)

        no_results_label = tk.Label(dialog, text="No products found matching your search.", fg="red")

        # --- End Search Functionality ---

        top_frame = tk.Frame(dialog)
        top_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        tk.Label(top_frame, text="Select ignore preferences for current & future updates:", font=("Arial", 12, "bold")).pack(pady=(0, 5))

        # Container for the list of products
        list_container = tk.Frame(dialog)
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        canvas = tk.Canvas(list_container)
        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        inner_frame = tk.Frame(canvas)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")

        # Store Checkbutton variables and product frames to manage their state
        self.dialog_vars = {}
        self.product_frames = {}

        # Display each update candidate with options
        for product in update_candidates:
            sku = product['sku']
            product_frame = tk.Frame(inner_frame, padx=5, pady=2, relief=tk.RAISED, borderwidth=1)
            product_frame.pack(fill=tk.X, padx=5, pady=2)
            self.product_frames[product['sku']] = product_frame

            # Labels for product info and changes
            name = product.get('name', 'N/A')
            display_text = _truncate(name)
            lbl = tk.Label(product_frame, text=display_text, font=("Arial", 10))
            lbl.pack(side=tk.LEFT, padx=5)
            tooltip_text = f"SKU: {product['sku']} - {name}"
            # always provide tooltip so SKU is accessible on hover
            ToolTip(lbl, tooltip_text)

            changes_text = ""
            if 'new_price' in product:
                changes_text += f"Price: {product['current_price']} -> {product['new_price']}"
            if 'new_stock' in product:
                if changes_text: changes_text += " | "
                changes_text += f"Stock: {product['current_stock']} -> {product['new_stock']}"
            tk.Label(product_frame, text=f"Changes: {changes_text}", fg="blue").pack(side=tk.LEFT, padx=10)

            # Checkboxes for CURRENT UPDATE (New temporary skip)
            # These variables are only for this single update run and are NOT saved to the database.
            skip_price_var = tk.IntVar()
            skip_stock_var = tk.IntVar()

            tk.Checkbutton(product_frame, text="Skip Price (Current Run Only)", variable=skip_price_var, fg="red").pack(side=tk.RIGHT, padx=5)
            tk.Checkbutton(product_frame, text="Skip Stock (Current Run Only)", variable=skip_stock_var, fg="red").pack(side=tk.RIGHT, padx=5)

            # Checkboxes for FUTURE/PERMANENT preferences (Existing functionality)
            # Find existing preference from the main preferences list
            current_pref = next(((s, p, st) for s, p, st in self.preferences if s == sku), None)
            permanent_ignore_price_var = tk.IntVar(value=current_pref[1] if current_pref else 0)
            permanent_ignore_stock_var = tk.IntVar(value=current_pref[2] if current_pref else 0)

            # Renamed the widgets and variables to be clearer
            tk.Checkbutton(product_frame, text="Ignore Price", variable=permanent_ignore_price_var).pack(side=tk.RIGHT, padx=5)
            tk.Checkbutton(product_frame, text="Ignore Stock", variable=permanent_ignore_stock_var).pack(side=tk.RIGHT, padx=5)

            self.dialog_vars[product['sku']] = {
                'skip_price': skip_price_var,               # <-- NEW
                'skip_stock': skip_stock_var,               # <-- NEW
                'ignore_price': permanent_ignore_price_var, # <-- RENAMED
                'ignore_stock': permanent_ignore_stock_var  # <-- RENAMED
            }
            
        # Binding the mouse wheel events to the canvas
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Bind the mouse wheel event to the canvas
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # Function to update the scroll region
        def on_frame_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner_frame.bind("<Configure>", on_frame_configure)
    
        # This is the crucial part of the fix: forcing an initial update
        dialog.update_idletasks()
        on_frame_configure()

        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)

        def on_confirm():
            final_update_candidates = []
            new_ignore_preferences = []

            #for product in update_candidates:
                #sku = product['sku']
                #vars = self.dialog_vars.get(sku)

                ## Collect preferences to be saved before checking for updates
                #if vars['ignore_price'].get() or vars['ignore_stock'].get():
                    #new_ignore_preferences.append((sku, vars['ignore_price'].get(), vars['ignore_stock'].get()))

                ## Remove updates from the current list if they are ignored
                #if vars['ignore_price'].get():
                    #product.pop('new_price', None)
                #if vars['ignore_stock'].get():
                    #product.pop('new_stock', None)

                ## Only add to final update candidates if there's still something to update
                #if 'new_price' in product or 'new_stock' in product:
                    #final_update_candidates.append(product)
            for product in update_candidates:
                sku = product['sku']
                vars = self.dialog_vars.get(sku)

                # --- 1. COLLECT PERMANENT PREFERENCES TO SAVE (Existing Logic) ---
                # Check the PERMANENT ignore variables for saving to DB
                permanent_price_flag = vars['ignore_price'].get()
                permanent_stock_flag = vars['ignore_stock'].get()
                
                if permanent_price_flag or permanent_stock_flag:
                    new_ignore_preferences.append((sku, permanent_price_flag, permanent_stock_flag))

                # --- 2. DETERMINE CURRENT RUN UPDATE STATUS (New/Modified Logic) ---
                
                # Check both the PERMANENT ignore and the NEW TEMPORARY skip variables
                # A product is skipped for the current run if *either* checkbox is checked.
                skip_price_current_run = permanent_price_flag or vars['skip_price'].get()
                skip_stock_current_run = permanent_stock_flag or vars['skip_stock'].get()

                # Remove updates from the current product if they are permanently ignored OR temporarily skipped
                if skip_price_current_run:
                    product.pop('new_price', None)
                if skip_stock_current_run:
                    product.pop('new_stock', None)

                # Only add to final update candidates if there's still something to update
                if 'new_price' in product or 'new_stock' in product:
                    final_update_candidates.append(product)

            dialog.destroy()

            # --- Start of Combined Preference Management ---
            # This block now runs regardless of update candidates
            updated_preferences = list(self.preferences)

            skus_to_update = {sku for sku, _, _ in new_ignore_preferences}
            for sku, price_flag, stock_flag in new_ignore_preferences:
                found = False
                for i, (s, p, st) in enumerate(updated_preferences):
                    if s == sku:
                        updated_preferences[i] = (sku, price_flag, stock_flag)
                        found = True
                        break
                if not found:
                    updated_preferences.append((sku, price_flag, stock_flag))

            # This part of the logic correctly removes preferences that were unchecked
            self.preferences = [pref for pref in updated_preferences if pref[0] not in skus_to_update or (pref[0] in skus_to_update and (pref[1] or pref[2]))]

            self.update_preferences_listbox()
            self.db.save_sku_preferences(self.preferences)
            self.log("New SKU ignore preferences have been saved.")
            # --- End of Combined Preference Management ---

            # Now, check if there's anything to update and proceed
            if not final_update_candidates:
                messagebox.showinfo("Info", "No products selected for update.")
                return  # Exit the function

            self.log("Performing bulk update on selected products...")
            checker = WooCommerceInventoryChecker(
                self.store_url_entry.get().strip(),
                self.consumer_key_entry.get().strip(),
                self.consumer_secret_entry.get().strip(),
                self.log_queue
            )
            thread = threading.Thread(target=checker.bulk_update_with_user_input,
                                        args=(self.csv_filepath, final_update_candidates))
            thread.daemon = True
            thread.start()

        tk.Button(button_frame, text="Perform Update", command=on_confirm, padx=10, pady=5, bg="#3B82F6", fg="white", activebackground="#2563EB").pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy, padx=10, pady=5, bg="#9CA3AF", fg="white", activebackground="#6B7280").pack(side=tk.LEFT)
if __name__ == "__main__": 
    
    # Set up the main GUI window 
    root = tk.Tk() 
    app = App(root) 
    root.mainloop()