import tkinter as tk
import csv
from tkinter import filedialog, messagebox, scrolledtext
import threading
import queue
import os
from utils import _read_csv
from dbManager import DatabaseManager
from wcChecker import WooCommerceInventoryChecker
import json
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
        self.download_report_button = None

        # Main frame with some padding 
        main_frame = tk.Frame(root, padx=20, pady=20, bg="#F3F4F6") 
        main_frame.pack(fill=tk.BOTH, expand=True) 
        self.main_frame = main_frame
        
        # Credentials and File section 
        credentials_frame = tk.LabelFrame(main_frame, text="Credentials & File", padx=10, pady=10, bg="#E5E7EB", font=("Arial", 10, "bold")) 
        credentials_frame.pack(fill=tk.X, pady=10) 

        # Store URL 
        tk.Label(credentials_frame, text="Store URL:", bg="#E5E7EB").grid(row=0, column=0, sticky="w", padx=5, pady=2) 
        self.store_url_entry = tk.Entry(credentials_frame, width=50) 
        self.store_url_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew") 

        tk.Button(credentials_frame, text="Save Credentials", command=self.save_credentials, 
                    bg="#9CA3AF", fg="white", activebackground="#6B7280", relief=tk.RAISED, 
                    bd=3, padx=10).grid(row=2, column=2, padx=5, pady=2, sticky="e")

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
        
        self.loadProductsButton = tk.Button(button_frame, text="Load Products from Store", command=self.run_product_load,
                  bg="#4F46E5", fg="white", activebackground="#3730A3", relief=tk.RAISED,
                  bd=3, padx=10)
        self.loadProductsButton.pack(side=tk.LEFT, padx=10)

        self.missingCheckButton = tk.Button(button_frame, text="Check for Missing Products", command=self.run_missing_check, 
                    bg="#10B981", fg="white", activebackground="#059669", relief=tk.RAISED, 
                    bd=3, padx=10)
        self.missingCheckButton.pack(side=tk.LEFT, padx=10) 
        
        self.bulkUpdateButton = tk.Button(button_frame, text="Bulk Update Inventory", command=self.run_bulk_update, 
                    bg="#3B82F6", fg="white", activebackground="#2563EB", relief=tk.RAISED, 
                    bd=3, padx=10)
        self.bulkUpdateButton.pack(side=tk.LEFT, padx=10) 
        
        # sales analysis button
        self.salesAnalysisButton = tk.Button(button_frame, text="Analyze Sales Report", command=self.run_sales_analysis,
                    bg="#7C3AED", fg="white", activebackground="#5B21B6", relief=tk.RAISED,
                    bd=3, padx=10)
        self.salesAnalysisButton.pack(side=tk.LEFT, padx=10)

        self.skuCheckButton = tk.Button(button_frame, text="Check Specific SKUs", command=self.show_sku_check_dialog, 
                    bg="#F59E0B", fg="white", activebackground="#D97706", relief=tk.RAISED, 
                    bd=3, padx=10)
        self.skuCheckButton.pack(side=tk.LEFT, padx=10)

        # Log section 
        self.log_frame = tk.LabelFrame(main_frame, text="Activity Log", padx=10, pady=10, bg="#F3F4F6", font=("Arial", 10, "bold")) 
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=10) 
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, state=tk.DISABLED, bg="#1F2937", fg="#E5E7EB") 
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
        credentials = {
            "url": self.store_url_entry.get().strip(),
            "key": self.consumer_key_entry.get().strip(),
            "secret": self.consumer_secret_entry.get().strip()
        }

        # check if any field is empty
        if not all(credentials.values()):
            self.log("Error: Please fill in all credentials.")
            messagebox.showerror("Error", "Please fill in all credentials.")
            return None

        return credentials

    def run_product_load(self):
        """
        Starts the process of fetching all products from the store.
        """
        creds = self.get_credentials()

        self.log_text.delete(1.0, tk.END)
        self.log("Fetching all products from store...")
        
        self.product_queue = queue.Queue()
        checker = WooCommerceInventoryChecker(
            creds["url"],
            creds["key"],
            creds["secret"],
            self.log_queue
        )
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
        creds = self.get_credentials() 
        if creds is None:
            return
        skus_to_ignore = [sku for sku, _, _ in self.preferences] 

        if not self.wc_product_cache:
            messagebox.showerror("Error", "Please load products from the store first.")
            return

        self.log_text.delete(1.0, tk.END) 
        self.log("Starting 'Check for Missing Products'...") 

        checker = WooCommerceInventoryChecker(
            creds["url"],
            creds["key"],
            creds["secret"],
            self.log_queue
        ) 
        thread = threading.Thread(target=checker.find_missing_in_csv, args=(self.csv_filepath, set(skus_to_ignore), self.wc_product_cache)) 
        thread.daemon = True 
        thread.start() 

    def run_sales_analysis(self):
        """
        Prompts the user for a sales report CSV and logs any SKUs sold
        that do not exist on the WooCommerce website.
        """
        if not self.wc_product_cache:
            messagebox.showerror("Error", "Please load products from the store first.")
            return

        sales_filepath = filedialog.askopenfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not sales_filepath:
            self.log("Sales file selection cancelled.")
            return

        self.log_text.delete(1.0, tk.END)
        self.log("Analyzing sales report against website products...")

        creds = self.get_credentials()
        if creds is None:
            return

        checker = WooCommerceInventoryChecker(
            creds["url"],
            creds["key"],
            creds["secret"],
            self.log_queue
        )
        thread = threading.Thread(target=checker.analyze_sales, args=(sales_filepath, self.wc_product_cache, self.csv_filepath))
        thread.daemon = True
        thread.start()

    def run_bulk_update(self): 
        """ 
        Starts the bulk update operation by first finding candidates, then 
        prompting the user for exclusion, and finally performing the update. 
        """ 
        creds = self.get_credentials() 

        if not self.wc_product_cache:
            messagebox.showerror("Error", "Please load products from the store first.")
            return

        self.log_text.delete(1.0, tk.END) 
        self.log("Starting 'Bulk Update Inventory'...") 

        checker = WooCommerceInventoryChecker(
            creds["url"],
            creds["key"],
            creds["secret"],
            self.log_queue
        ) 
        
        # Create a dictionary for quick lookup of ignore preferences 
        ignore_preferences = {sku: {'price': bool(price_flag), 'stock': bool(stock_flag)} for sku, price_flag, stock_flag in self.preferences} 

        # This part of the logic needs to run in a thread to not freeze the GUI 
        def find_candidates_and_prompt(): 
            csv_data = _read_csv(self.csv_filepath) 
            all_wc_products = list(self.wc_product_cache.values())

            if not csv_data: 
                return 

            update_candidates = [] 
            checker._log("\nStep 3: Comparing data and identifying update candidates...") 
            for wc_product in all_wc_products: 
                is_managing_stock = wc_product.get('manage_stock', False)
                sku = wc_product.get('sku') 
                
                if sku and sku in csv_data: 
                    csv_product = csv_data[sku] 
                    #print(csv_product)
                    wc_price_str = wc_product.get('regular_price', '0')
                    if wc_price_str == "":
                        wc_price_str = "0"  # default to 0 for comparison 
                    try:
                        wc_price = float(wc_price_str)
                    except ValueError:
                        checker._log(f"❌ Error: Skipping SKU '{sku}' due to invalid price format: '{wc_price_str}' in WooCommerce product data.")
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
                    if sku == "6290362340553":
                        print(f"Debug: WC Product: {wc_product}")
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
                    stock_changed = (wc_stock != csv_stock or not is_managing_stock) and not ignore_stock 
                    if sku == "6290362340553":
                        print(f"Debug: SKU: {sku}, WC Price: {wc_price}, CSV Price: {csv_price}, WC Stock: {wc_stock}, CSV Stock: {csv_stock}, Ignore Price: {ignore_price}, Ignore Stock: {ignore_stock}, Price Changed: {price_changed}, Stock Changed: {stock_changed}")

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
                            candidate_data['current_stock'] = wc_stock if is_managing_stock else "Not Managing Stock"
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

        The product names shown in this dialog are trimmed to a maximum length
        so that the layout remains tidy.  A tooltip is attached to every label
        (even when not truncated) so the full SKU and name are always available
        when the user hovers over the entry.  This ensures the SKU does not
        clutter the list but remains easily accessible.
        """
        # ---- helper utilities for this dialog ----
        def _truncate(text, max_len=50):
            if len(text) <= max_len:
                return text
            return text[: max_len - 3] + "..."

        class ToolTip:
            """Simple tooltip for a widget.  Adapted from common Tkinter recipes."""
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
            # only show the product name in the label, trimming it if too long
            name = product.get('name', 'N/A')
            display_text = _truncate(name)
            lbl = tk.Label(product_frame, text=display_text, font=("Arial", 10))
            lbl.pack(side=tk.LEFT, padx=5)
            # tooltip will include SKU + full name so the user can see both
            tooltip_text = f"SKU: {product['sku']} - {name}"
            if display_text != name:
                ToolTip(lbl, tooltip_text)
            else:
                # still attach tooltip so SKU is available on hover
                ToolTip(lbl, tooltip_text)

            if 'new_price' in product:
                new_price_text = f"Price: {product['current_price']} -> {product['new_price']}"
                if product['new_price'] <= 0:
                    text_color = "red"
                else:
                    text_color = "blue"
                tk.Label(product_frame, text=new_price_text, fg=text_color).pack(side=tk.LEFT, padx=5)
            if 'new_stock' in product:
                new_stock_text = f"Stock: {product['current_stock']} -> {product['new_stock']}"
                if product['new_stock'] < -1:
                    text_color = "red"
                else:
                    text_color = "blue"
                tk.Label(product_frame, text=new_stock_text, fg=text_color).pack(side=tk.LEFT, padx=5)

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
    # app.py (Modified function)

    def show_sku_check_dialog(self):
        """
        Creates a dialog window for the user to input a list of SKUs 
        either manually or by uploading a simple CSV file.
        """
        if not self.csv_filepath:
            messagebox.showerror("Error", "Please select a CSV file first.")
            return
        csv_data = _read_csv(self.csv_filepath)  

        if isinstance(csv_data, Exception):
            messagebox.showerror("Error", f"Failed to read CSV: {csv_data}")
            return
        try: 
            firstRowData = next(iter(csv_data.values()))
        except StopIteration:
            messagebox.showerror("Error", "The selected CSV file is empty.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Check Specific SKUs")
        dialog.geometry("500x450")
        dialog.transient(self.root)
        dialog.grab_set()

        # --- INPUT METHOD FRAME ---
        input_frame = tk.Frame(dialog, padx=10, pady=10)
        input_frame.pack(fill=tk.BOTH, expand=True)

        # 1. Manual Input Section
        tk.Label(input_frame, text="1. Enter SKUs (one per line):").pack(anchor="w")
        self.sku_input_text = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, height=10)
        self.sku_input_text.pack(fill=tk.X, pady=5)
    
        # 2. CSV Upload Section
        tk.Label(input_frame, text="2. Or Upload a single-column CSV file(no headings just sku's):").pack(anchor="w", pady=(10, 0))
    
        file_frame = tk.Frame(input_frame)
        file_frame.pack(fill=tk.X, pady=5)
    
        self.sku_check_csv_path = None # Instance variable to store the path
        self.sku_csv_label = tk.Label(file_frame, text="No CSV selected", anchor="w", fg="gray")
        self.sku_csv_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(file_frame, text="Browse CSV...", command=self.browse_sku_csv).pack(side=tk.RIGHT)

        # --- BUTTONS ---
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)

        def start_check():
            sku_list = self._get_skus_from_dialog() # Use the new combined function
        
            if not sku_list:
                messagebox.showerror("Error", "Please enter SKUs manually or upload a CSV file.")
                return

            dialog.destroy() # Close the input dialog
            self.run_specific_sku_check(sku_list)

        tk.Button(button_frame, text="Start Check", command=start_check, padx=10, pady=5, bg="#3B82F6", fg="white", activebackground="#2563EB").pack(side=tk.LEFT, padx=10)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy, padx=10, pady=5, bg="#9CA3AF", fg="white", activebackground="#6B7280").pack(side=tk.LEFT)
    #def show_sku_check_dialog(self):
        #"""
        #Creates a dialog window for the user to input a list of SKUs.
        #"""
        #dialog = tk.Toplevel(self.root)
        #dialog.title("Check Specific SKUs")
        #dialog.geometry("500x400")
        #dialog.transient(self.root)
        #dialog.grab_set()

        #tk.Label(dialog, text="Enter SKUs (one per line):").pack(pady=10)
        
        #self.sku_input_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, height=10)
        #self.sku_input_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

        #button_frame = tk.Frame(dialog)
        #button_frame.pack(pady=10)

        #def start_check():
            #sku_list_raw = self.sku_input_text.get("1.0", tk.END).strip()
            #if not sku_list_raw:
                #messagebox.showerror("Error", "Please enter at least one SKU.")
                #return

            #sku_list = sku_list_raw.splitlines()
            #dialog.destroy() # Close the input dialog
            #self.run_specific_sku_check(sku_list)

        #tk.Button(button_frame, text="Start Check", command=start_check, padx=10, pady=5, bg="#3B82F6", fg="white", activebackground="#2563EB").pack(side=tk.LEFT, padx=10)
        #tk.Button(button_frame, text="Cancel", command=dialog.destroy, padx=10, pady=5, bg="#9CA3AF", fg="white", activebackground="#6B7280").pack(side=tk.LEFT)

    def run_specific_sku_check(self, sku_list):
        """
        Starts a thread to check the provided list of SKUs and display results.
        """
        creds = self.get_credentials()
        if not all(creds.values()):
            return # get_credentials handles the error message

        self.log("Starting specific SKU inventory check...")
        self.set_ui_busy(True)

        checker = WooCommerceInventoryChecker(
            creds['url'],
            creds['key'],
            creds['secret'],
            self.log_queue
        )
        if not self.csv_filepath:
            self.log("Error: No CSV file selected.")
            self.set_ui_busy(False)
            return
        csv_data = _read_csv(self.csv_filepath)
        
        # We need a new queue to pass the results back from the worker thread
        # Initialize the thread-safe queue
        results_queue = queue.Queue() 

        # Create and start the worker thread
        thread = threading.Thread(
            target=checker.check_specific_skus, # The worker function in wc_checker.py
            args=(sku_list, results_queue, csv_data)      # Pass the SKUs and the queue
        )
        thread.daemon = True # Allows the program to exit even if the thread is running
        thread.start()

        # Start checking the queue for results every 100ms
        self.root.after(100, self._check_sku_results_queue, results_queue, thread)
    def set_ui_busy(self, is_busy):
        """
        Enables or disables the main action buttons to prevent concurrent 
        network operations and provides visual feedback.
        """
        # 1. Define the list of buttons to control
        main_buttons = [
            self.loadProductsButton, 
            self.missingCheckButton,
            self.bulkUpdateButton,
            self.skuCheckButton
        ]
    
        # 2. Determine the state
        # tk.DISABLED if True (busy), tk.NORMAL if False (not busy)
        state = tk.DISABLED if is_busy else tk.NORMAL
    
        # 3. Apply the state to all main buttons
        for button in main_buttons:
            # The button might not exist yet if called during initialization, 
            # but the try/except handles that safely.
            try:
                button.config(state=state)
            except AttributeError:
                # This is safe because we know the button variables exist later
                pass
    
        # 4. Update the cursor for clear visual feedback
        self.root.config(cursor="wait" if is_busy else "")
    # app.py (Add this method inside the App class)
    # app.py (REPLACE YOUR EXISTING _check_sku_results_queue ENTIRELY)

    def _check_sku_results_queue(self, results_queue, worker_thread):
        """
        Checks the results queue for data from the worker thread.
        This method is called repeatedly by self.root.after().
        """
        # 1. Check if the thread is still running
        if worker_thread.is_alive():
            # If still alive, check again in 100 milliseconds
            self.root.after(100, self._check_sku_results_queue, results_queue, worker_thread)
            return

        # 2. Thread has finished, now safely retrieve the results
        self.set_ui_busy(False)
    
        # Ensure there are results in the queue before trying to get them
        if results_queue.empty():
            self.log("Thread finished, but no results were found in the queue.")
            return

        # Get the results list from the queue
        sku_results = results_queue.get() 
        #print(json.dumps(sku_results, indent=2))  # For debugging purposes
    
        # --- CRITICAL ACTION: CALL THE HANDLER THAT DISPLAYS RESULTS AND CREATES BUTTON ---
        self._display_and_handle_sku_results(sku_results)
        # ---------------------------------------------------------------------------------
    
    def browse_sku_csv(self):
        """
        Opens a dialog for the user to select the SKU list CSV file.
        """
        filepath = filedialog.askopenfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filepath:
            self.sku_check_csv_path = filepath
            self.sku_csv_label.config(text=os.path.basename(filepath), fg="black")

    def _get_skus_from_dialog(self):
        """
        Retrieves SKUs from either the manual input box or the selected CSV file.
        Returns a cleaned list of SKUs.
        """
        sku_list = []
    
        # 1. Check for manual input
        manual_input = self.sku_input_text.get("1.0", tk.END).strip()
        if manual_input:
            # Split by newlines, handling mixed Windows/Linux line endings
            sku_list.extend([sku.strip() for sku in manual_input.splitlines() if sku.strip()])
    
        # 2. Check for CSV file input
        elif self.sku_check_csv_path and os.path.exists(self.sku_check_csv_path):
            try:
                with open(self.sku_check_csv_path, mode='r', encoding='utf-8') as file:
                    # Use a standard reader since there's no header
                    reader = csv.reader(file) 
                    for row in reader:
                        # Expecting only one column (the SKU)
                        if row and row[0].strip():
                            sku_list.append(row[0].strip())
            
                # Clear manual input field after successful CSV read for clarity
                self.sku_input_text.delete("1.0", tk.END)
                self.log(f"Loaded {len(sku_list)} SKUs from CSV: {os.path.basename(self.sku_check_csv_path)}")
            
            except Exception as e:
                self.log(f"Error reading SKU CSV file: {e}")
                messagebox.showerror("File Error", f"Could not read CSV file: {e}")
                return [] # Return empty list on error
            
        # Remove duplicates and ensure list is clean before returning
        return [sku.strip() for sku in set(sku_list) if sku.strip()]

    def _display_and_handle_sku_results(self, sku_results):
        """
        Organizes results, displays them in the log, and enables the report download button.
        """
        # 1. Initialize instance variable to hold the results for download
        self.last_sku_check_results = sku_results
    
        # 2. Organize the results into categories
        found_instock = []
        found_outofstock = []
        not_found = []
    
        for item in sku_results:
            if item['status'] == 'FOUND':
                if item['stock'] == 'INSTOCK':
                    found_instock.append(item)
                else:
                    found_outofstock.append(item)
            else:
                not_found.append(item)

        # Combine results in the desired order
        organized_results = found_instock + found_outofstock + not_found
    
        # 3. Log the organized output
        self.log("\n--- Specific SKU Check Results ---")
        self.log(f"Summary: {len(found_instock) + len(found_outofstock)} Found, {len(not_found)} Not Found.")
    
        self.log("\n--- FOUND & IN STOCK ---")
        for item in found_instock:
            self.log(f"  ✅ SKU: {item['sku']} | Title: {item['title']} | Qty: {item['quantity']}")

        self.log("\n--- FOUND & OUT OF STOCK ---")
        for item in found_outofstock:
            self.log(f"  ⚠️ SKU: {item['sku']} | Title: {item['title']} | Qty: {item['quantity']}")

        self.log("\n--- NOT FOUND IN STORE ---")
        for item in not_found:
            self.log(f"  ❌ SKU: {item['sku']} | Title: {item['title']} | Status: NOT FOUND")
        
        self.log("----------------------------------\n")
    
        # 4. Add the Download Report Button
        self._add_sku_report_button(organized_results)
    def _add_sku_report_button(self, organized_results):
        """
        Creates a temporary button to download the report and places it 
        inside the Activity Log frame.
        """
        # 1. Clean up any existing download button
        if hasattr(self, 'download_report_button') and self.download_report_button:
            self.download_report_button.destroy()

        # --- FIX: Temporarily UNPACK the log_text widget ---
        # This frees up the space so the button can be placed.
        self.log_text.pack_forget() 

        # 2. Create the new button, parented to self.log_frame
        self.download_report_button = tk.Button(self.log_frame, 
                                                text="⬇️ Download SKU Report", 
                                                command=lambda: self.download_sku_report(organized_results),
                                                bg="#10B981", fg="white", 
                                                activebackground="#059669")

        # 3. Pack the button first (it will be at the top)
        # Use 'before' or 'after' or just reverse the packing order (easiest)
        self.download_report_button.pack(fill=tk.X, pady=(0, 5))

        # --- FIX: RE-PACK the log_text widget (it will take the remaining space) ---
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def download_sku_report(self, sku_results):
        """
        Saves the organized SKU check results to a CSV file.
        """
        if not sku_results:
            messagebox.showinfo("Report Empty", "No results were generated to download.")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="SKU_Inventory_Report.csv"
        )

        if filepath:
            try:
                with open(filepath, 'w', newline='', encoding='utf-8') as file:
                    fieldnames = ['SKU', 'Title', 'Status', 'Stock Status', 'Quantity']
                    writer = csv.DictWriter(file, fieldnames=fieldnames)

                    writer.writeheader()
                    for item in sku_results:
                        writer.writerow({
                            'SKU': item['sku'],
                            'Title': item['title'],
                            'Status': item['status'],
                            'Stock Status': item['stock'],
                            'Quantity': item['quantity']
                        })
            
                self.log(f"Successfully saved report to: {os.path.basename(filepath)}")
                messagebox.showinfo("Success", f"Report successfully saved to {filepath}")
            
            except Exception as e:
                self.log(f"Error saving report: {e}")
                messagebox.showerror("Error", f"Could not save report: {e}")
            
        # Remove the button after download or if dialog is cancelled
        if hasattr(self, 'download_report_button') and self.download_report_button:
            self.download_report_button.destroy()
            self.download_report_button = None
            self.log_text.pack(fill=tk.BOTH, expand=True)
    
if __name__ == "__main__": 
    # Set up the main GUI window 
    root = tk.Tk() 
    app = App(root) 
    root.mainloop()