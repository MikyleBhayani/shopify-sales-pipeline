import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st

NAVY, LIGHT, GRAY = "#1E2D7D", "#8FA3E0", "#C9CED9"
px.defaults.color_discrete_sequence = [NAVY]

st.set_page_config(page_title="Sales Dashboard", layout="wide")
st.title("Sales Dashboard")

conn = sqlite3.connect("data/sales.db")
orders = pd.read_sql("SELECT * FROM orders WHERE payment_status = 'PAID'", conn)
products = pd.read_sql("SELECT * FROM products", conn)
conn.close()

orders["date"] = pd.to_datetime(orders["created_at"].str[:10])

ranges = {
    "All time": None,
    "Past year": pd.DateOffset(years=1),
    "Past 6 months": pd.DateOffset(months=6),
    "Past 3 months": pd.DateOffset(months=3),
    "Past month": pd.DateOffset(months=1),
    "Past week": pd.DateOffset(weeks=1),
    "Today": pd.DateOffset(days=1),
}
period = st.segmented_control("Time range", list(ranges), default="All time") or "All time"
if period != "All time":
    orders = orders[orders["date"] > pd.Timestamp.today().normalize() - ranges[period]]

if orders.empty:
    st.info("No paid orders in this time range.")
    st.stop()

orders["day"] = orders["date"].dt.day_name()
orders["month"] = orders["date"].dt.strftime("%b")

products = products[products["order"].isin(orders["order"])]
products["revenue"] = products["quantity"] * products["product_price"]
products["category"] = "Accessories"
products.loc[products["title"].str.contains("door", case=False), "category"] = "Entry doors"
# garage runs last so "Garage Door" titles don't stay tagged as entry doors
products.loc[products["title"].str.contains("garage", case=False), "category"] = "Garage doors"

by_state = orders.groupby(["state", "state_code"])["subtotal"].sum().reset_index()
by_state = by_state.sort_values("subtotal", ascending=False)


def bar(df, x, y, label, money=False):
    fig = px.bar(df, x=x, y=y, labels={x: "", y: label}, height=300)
    if money:
        fig.update_layout(yaxis_tickprefix="$")
    return fig


def hbar(df, x, y, **kwargs):
    fig = px.bar(df, x=x, y=y, orientation="h", labels={x: "Revenue", y: ""}, height=380, **kwargs)
    fig.update_layout(yaxis_autorange="reversed", xaxis_tickprefix="$")
    return fig


c1, c2, c3, c4 = st.columns(4)
c1.metric("Total revenue", f"${orders['subtotal'].sum():,.0f}", border=True)
c2.metric("Orders", f"{len(orders):,}", border=True)
c3.metric("Average order", f"${orders['subtotal'].mean():,.0f}", border=True)
c4.metric("Top state", by_state["state"].iloc[0] if len(by_state) else "—", border=True)

daily = period in ("Past month", "Past week", "Today")
orders["period"] = orders["date"] if daily else orders["date"].dt.to_period("W").dt.start_time
revenue = orders.groupby("period")["subtotal"].sum().reset_index()

with st.container(border=True):
    st.subheader("Revenue per day" if daily else "Revenue per week")
    st.plotly_chart(bar(revenue, "period", "subtotal", "Revenue", money=True))

fig_map = px.choropleth(by_state, locations="state_code", locationmode="USA-states", color="subtotal",
                        scope="usa", color_continuous_scale="Blues", labels={"subtotal": "Revenue"}, height=380)
fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0), geo_bgcolor="rgba(0,0,0,0)")

left, right = st.columns([3, 2])
with left.container(border=True):
    st.subheader("Revenue by state")
    st.plotly_chart(fig_map)
with right.container(border=True):
    st.subheader("Top 10 states")
    st.plotly_chart(hbar(by_state.head(10), "subtotal", "state"))

best = products.groupby("title")[["revenue", "quantity"]].sum().reset_index()
best = best.nlargest(8, "revenue").rename(columns={"quantity": "Units sold"})
best["title"] = best["title"].str[:40]

split = products.groupby("category")["revenue"].sum().reset_index()
fig_split = px.pie(split, names="category", values="revenue", hole=0.55, color="category", height=380,
                   color_discrete_map={"Garage doors": NAVY, "Entry doors": LIGHT, "Accessories": GRAY})
fig_split.update_layout(legend_orientation="h")

left, right = st.columns([3, 2])
with left.container(border=True):
    st.subheader("Best-selling products")
    st.plotly_chart(hbar(best, "revenue", "title", hover_data=["Units sold"]))
with right.container(border=True):
    st.subheader("Garage vs. entry doors")
    st.plotly_chart(fig_split)

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

for box, (title, col, labels) in zip(st.columns(2), [("By day of week", "day", days), ("By month", "month", months)]):
    totals = orders.groupby(col).agg(orders=("order", "count"), revenue=("subtotal", "sum"))
    totals = totals.reindex(labels, fill_value=0).rename_axis(col).reset_index()
    with box.container(border=True):
        st.subheader(title)
        tab1, tab2 = st.tabs(["Orders", "Revenue"])
        tab1.plotly_chart(bar(totals, col, "orders", "Orders"))
        tab2.plotly_chart(bar(totals, col, "revenue", "Revenue", money=True))