from woocommerce import API
import os
import csv
import queue
import json

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
    
    def analyze_sales(self, sales_filepath, wc_product_cache, csv_filepath=None):
        """
        Reads a sales report CSV and logs SKUs that appear on the sales
        feed but do not exist in the WooCommerce product cache.  Intended to be
        run in a background thread.
        
        If csv_filepath is provided, will also include current stock levels
        from that inventory CSV in the output.
        """
        if not os.path.exists(sales_filepath):
            self._log(f"Error: The file '{sales_filepath}' was not found.")
            return
        if not wc_product_cache:
            self._log("Product cache is empty. Please load products first.")
            return

        # Load stock data from inventory CSV if provided
        stock_data = {}
        if csv_filepath and os.path.exists(csv_filepath):
            self._log(f"Reading stock levels from {os.path.basename(csv_filepath)}...")
            try:
                with open(csv_filepath, mode='r', encoding='utf-8') as file:
                    reader = csv.DictReader(file)
                    if reader.fieldnames and 'Item Code' in reader.fieldnames:
                        for row in reader:
                            item_code = row.get('Item Code')
                            if item_code:
                                sku = item_code.strip()
                                stock_raw = row.get('On Hand', 0)
                                try:
                                    stock = int(float(stock_raw)) if stock_raw not in (None, "") else 0
                                except ValueError:
                                    stock = 0
                                stock_data[sku] = stock
            except Exception as e:
                self._log(f"Warning: Could not read stock from inventory CSV: {e}")

        self._log("Step 1: Reading sales data from CSV file...")
        sold_skus = {}  # mapping sku -> {'qty': total_qty, 'description': description}
        skipped_count = 0
        try:
            with open(sales_filepath, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                if 'Item Code' not in reader.fieldnames:
                    self._log("Error: Sales CSV must contain a column named 'Item Code'.")
                    return

                for row in reader:
                    item_code = row.get('Item Code')
                    if item_code:
                        sku = item_code.strip()
                        qty_raw = row.get('Qty. Sold', 0)
                        description = row.get('Description', 'N/A')
                        try:
                            qty = float(qty_raw) if qty_raw not in (None, "") else 0
                        except ValueError:
                            qty = 0
                        if sku in sold_skus:
                            sold_skus[sku]['qty'] += qty
                        else:
                            sold_skus[sku] = {'qty': qty, 'description': description}
                    else:
                        skipped_count += 1
        except Exception as e:
            self._log(f"Error reading sales CSV: {e}")
            return

        self._log(f"Found {len(sold_skus)} distinct SKUs in the sales report.")
        if skipped_count > 0:
            self._log(f"Skipped {skipped_count} rows due to missing 'Item Code'.")

        self._log("Step 2: Identifying SKUs sold but not present on website...")
        missing = [(sku, sold_skus[sku]) for sku in sold_skus if sku not in wc_product_cache]
        if missing:
            self._log(f"Found {len(missing)} SKUs sold but not in WooCommerce:")
            for sku, data in missing:
                qty = data['qty']
                desc = data['description']
                stock = stock_data.get(sku, 'N/A')
                stock_str = f" | Stock: {stock}" if stock_data else ""
                self._log(f"- {sku} | {desc} | Qty sold: {qty}{stock_str}")
        else:
            self._log("All sold SKUs exist on the website.")
        self._log("Analysis complete.")

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

    def check_specific_skus(self, sku_list, results_queue, csv_data):
        """
        Checks a specific list of SKUs against the WooCommerce store 
        and reports their stock status.
        """
        if not sku_list:
            self._log("Error: SKU list is empty.")
            return []

        # Remove duplicates and clean up the list
        clean_sku_list = [sku.strip() for sku in set(sku_list) if sku.strip()]
        
        self._log(f"\nSearching for {len(clean_sku_list)} unique SKUs in the store...")
        
        # WooCommerce API can search by SKU directly, but it's more efficient 
        # to use the 'sku' parameter for exact matching and filter later.
        
        results = []
        batch_size = 50 # API search limits can be restrictive; keep batch size small
        
        for i in range(0, len(clean_sku_list), batch_size):
            sku_batch = clean_sku_list[i:i + batch_size]
            sku_query = ','.join(sku_batch)
            
            self._log(f"Querying batch {int(i/batch_size) + 1}...")
            
            try:
                # The 'sku' parameter is the most direct way to filter a list of SKUs
                response = self.wcapi.get("products", params={"sku": sku_query, "per_page": batch_size, "status": "any"})
                print(f"Response for batch {int(i/batch_size) + 1}: {response.status_code} - {response.text}")  # Debugging line
                
                if response.status_code not in [200, 201]:
                    self._log(f"Error: API status code {response.status_code} in batch {int(i/batch_size) + 1}. Response: {response.text}")
                    continue

                products = response.json()
                
                # Check for each SKU in the batch what the status is
                for sku in sku_batch:
                    found_product = next((p for p in products if p.get('sku') == sku), None)
                    
                    if found_product:
                        # Status will be 'instock' or 'outofstock'
                        stock_status = found_product.get('stock_status', 'N/A').upper()
                        stock_quantity = found_product.get('stock_quantity', 'N/A')
                        product_name = found_product.get('name', 'N/A')
                        
                        results.append({
                            'sku': sku,
                            'status': 'FOUND',
                            'stock': stock_status,
                            'quantity': stock_quantity,
                            'title': product_name
                        })
                    else:
                        title = csv_data[sku]['Description'] if sku in csv_data else 'N/A'
                        results.append({
                            'sku': sku,
                            'status': 'NOT FOUND',
                            'stock': 'N/A',
                            'quantity': 'N/A',
                            'title': title
                        })
            
            except Exception as e:
                self._log(f"An unexpected error occurred during batch query: {e}")
                
        self._log("\nSpecific SKU check complete.")
        results_queue.put(results)
        print(json.dumps(results, indent=2))  # For debugging purposes