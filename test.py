from utils import _read_csv
import json
csv_filepath = "./PRICES.CSV"

csv_data = _read_csv(csv_filepath)
print(json.dumps(csv_data, indent=2))