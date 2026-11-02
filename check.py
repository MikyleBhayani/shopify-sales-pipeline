import sqlite3
import pandas as pd

conn = sqlite3.connect("data/sales.db")
print(pd.read_sql("SELECT * FROM orders", conn))
print(pd.read_sql("SELECT * FROM products", conn))