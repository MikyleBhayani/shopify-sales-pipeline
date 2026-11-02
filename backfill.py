import requests
import pandas as pd
import sqlite3
import time
from storeinfo import STORE, CLIENT_ID, CLIENT_SECRET
import os

token_response = requests.post(
    f"https://{STORE}/admin/oauth/access_token",
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
)

TOKEN = token_response.json()["access_token"]

query = """
query ($cursor: String) {
  orders(first: 50, after: $cursor) {
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
    pageInfo { hasNextPage endCursor }
  }
}
"""

orders = []
cursor = None

while True:
    response = requests.post(
        f"https://{STORE}/admin/api/2026-10/graphql.json",
        headers={"X-Shopify-Access-Token": TOKEN},
        json={"query": query, "variables": {"cursor": cursor}},
    )
    page = response.json()["data"]["orders"]
    orders = orders + page["nodes"]
    print(len(orders), "orders so far")
    if not page["pageInfo"]["hasNextPage"]:
        break
    cursor = page["pageInfo"]["endCursor"]
    time.sleep(1)

df = pd.json_normalize(orders)
products = pd.json_normalize(orders, record_path=["lineItems", "nodes"], meta=["name"])

df = df.drop(columns=["shippingAddress", "customer", "lineItems.nodes"], errors="ignore")
df["shippingAddress.province"] = df["shippingAddress.province"].fillna("Pickup Order")

df = df.rename(columns={
    "name": "order",
    "createdAt": "created_at",
    "displayFinancialStatus": "payment_status",
    "subtotalPriceSet.shopMoney.amount": "subtotal",
    "totalDiscountsSet.shopMoney.amount": "discounts",
    "totalPriceSet.shopMoney.amount": "total",
    "shippingAddress.province": "state",
    "shippingAddress.provinceCode": "state_code",
    "customer.id": "customer_id",
})
df[["subtotal", "discounts", "total"]] = df[["subtotal", "discounts", "total"]].astype(float)

products = products.rename(columns={
    "name": "order",
    "originalUnitPriceSet.shopMoney.amount": "product_price",
})
products["product_price"] = products["product_price"].astype(float)

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

print("Done:", len(df), "orders and", len(products), "products saved")