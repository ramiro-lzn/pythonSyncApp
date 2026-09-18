import csv
def _read_csv(csv_filepath):
    """ 
    Reads product data from a CSV file. 
    Returns a dictionary of data on success, or the Exception object on failure.
    """ 
    try: 
        with open(csv_filepath, mode='r', encoding='utf-8') as file: 
            reader = csv.DictReader(file) 
            
            required_fields = ['Item Code', 'Description', 'Price', 'On Hand']
            if not all(field in reader.fieldnames for field in required_fields): 
                # Raise a specific error for missing columns
                # This makes it easy for the caller to identify the type of error
                raise ValueError("CSV file must contain columns 'Item Code', 'Price', and 'On Hand'.") 
                
            csv_data = {} 
            for row in reader: 
                item_code = row.get('Item Code') 
                if item_code: 
                    csv_data[item_code.strip()] = row 
            
            return csv_data # Success: returns the dictionary
            
    except Exception as e: 
        # Failure: returns the exception object itself
        return e