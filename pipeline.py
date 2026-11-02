import requests
import pandas as pd
import os
import sqlite3
from datetime import date, timedelta
from storeinfo import STORE, CLIENT_ID, CLIENT_SECRET

# Get a temporary access token
token_response = requests.post(
    f"https://{STORE}/admin/oauth/access_token",
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
)
TOKEN = token_response.json()["access_token"]

# Ask for the last 8 days - Shopify plain date quirk leads to week needing 8 days not 7
week_ago = date.today() - timedelta(days=8)

query = """
{
  orders(first: 100, reverse: true, query: "created_at:>=WEEK_AGO") {
    nodes {
      name
      createdAt
      displayFinancialStatus
      subtotalPriceSet { shopMoney { amount } }
      totalDiscountsSet { shopMoney { amount } }
      totalPriceSet { shopMoney { amount } }
      shippingAddress { province provinceCode }
      customer { id }
      lineItems(first: 10) {
      nodes {
      title
      quantity
      originalUnitPriceSet { shopMoney { amount } }
      }
      }
    }
  }
}
"""
query = query.replace("WEEK_AGO", str(week_ago))

# Send the query, and stop early if there were no orders
response = requests.post(
    f"https://{STORE}/admin/api/2026-10/graphql.json",
    headers={"X-Shopify-Access-Token": TOKEN},
    json={"query": query},
)
# print(response.json())
orders = response.json()["data"]["orders"]["nodes"]

if not orders:
    print("No orders this week")
    exit()

# Split into two tables: one row per order, and one row per product bought
df = pd.json_normalize(orders)
products = pd.json_normalize(orders, record_path=["lineItems", "nodes"], meta=["name"])

# Clean the orders table
df = df.drop(columns=["shippingAddress", "customer", "lineItems.nodes"], errors="ignore")
df["shippingAddress.province"] = df["shippingAddress.province"].fillna("Pickup Order")
# print(df.columns)
df = df.rename(columns={
    "name": "order",
    "createdAt": "created_at",
    "displayFinancialStatus": "payment_status",
    "subtotalPriceSet.shopMoney.amount": "subtotal",
    "totalDiscountsSet.shopMoney.amount": "discounts",
    "totalPriceSet.shopMoney.amount": "total",
    "shippingAddress.province": "state",
    "customer.id": "customer_id",
    "shippingAddress.provinceCode": "state_code",
})
df[["subtotal", "discounts", "total"]] = df[["subtotal", "discounts", "total"]].astype(float)

# Clean the products table
products = products.rename(columns={
    "name": "order",
    "originalUnitPriceSet.shopMoney.amount":"product_price"})
products["product_price"] = products["product_price"].astype(float)

# Save to the database, deleting old copies of these orders first so nothing is doubled
os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/sales.db")

for order in df["order"]:
    try:
        conn.execute('DELETE FROM orders WHERE "order" = ?', [order])
        conn.execute('DELETE FROM products WHERE "order" = ?', [order])
    except sqlite3.OperationalError:
        pass
conn.commit()

df.to_sql("orders", conn, if_exists="append", index=False)
products.to_sql("products", conn, if_exists="append", index=False)
conn.close()

# Keep a CSV backup of this run
df.to_csv(f"data/orders_{date.today()}.csv", index=False)
products.to_csv(f"data/products_{date.today()}.csv", index=False)

# Confirmation Check
print(len(df), "orders saved")
