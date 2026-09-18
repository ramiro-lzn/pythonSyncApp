import csv
import sys

def read_and_print_csv(file_path):
    """
    Reads a CSV file and prints its contents row by row.
    """
    try:
        # 'utf-8-sig' handles Byte Order Mark (BOM) which can cause issues
        with open(file_path, 'r', newline='', encoding='utf-8-sig') as csv_file:
            reader = csv.DictReader(csv_file)
            
            # Print the field names (headers)
            print("CSV Headers:")
            print(reader.fieldnames)
            print("-" * 30)
            
            # Print each row of data
            print("CSV Data:")
            for row in reader:
                print(row)
            
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Check if a file path was provided as a command-line argument
    if len(sys.argv) < 2:
        print("Usage: python csv_reader_test.py <path_to_your_csv_file>")
    else:
        csv_file_path = sys.argv[1]
        read_and_print_csv(csv_file_path)