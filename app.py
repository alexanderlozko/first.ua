import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
import pycountry

# ==== 1. Читаємо дані ====
bets = pd.read_csv("bets.csv")
sessions = pd.read_csv("sessions.csv")
transactions = pd.read_csv("transactions.csv")
users = pd.read_csv("users.csv")

# ==== 2. Конвертуємо дати ====
bets["bet_time"] = pd.to_datetime(bets["bet_time"])
sessions["start_time"] = pd.to_datetime(sessions["start_time"])
sessions["end_time"] = pd.to_datetime(sessions["end_time"])
sessions["date"] = sessions["start_time"].dt.date
transactions["timestamp"] = pd.to_datetime(transactions["timestamp"])
users["registration_date"] = pd.to_datetime(users["registration_date"])

# ==== 3. Отримання множин користувачів за пристроями ====
def get_device_users(device):
    """Повертає множину користувачів для конкретного пристрою"""
    if device == "mobile":
        return set(sessions[sessions["device_type"] == "mobile"]["user_id"])
    elif device == "desktop":
        return set(sessions[sessions["device_type"] == "desktop"]["user_id"])
    elif device == "all":
        mobile_users = get_device_users("mobile")
        desktop_users = get_device_users("desktop")
        return mobile_users.union(desktop_users)
    return set()

# ==== 4. DAU / WAU / MAU ====
def calculate_metrics(device):
    """Підраховує DAU / WAU / MAU для конкретного пристрою"""
    if device == "all":
        # Для All беремо об’єднання користувачів з Mobile та Desktop
        dev_users = get_device_users("all")
        filtered_sessions = sessions[sessions["user_id"].isin(dev_users)]
    else:
        filtered_sessions = sessions[sessions["device_type"] == device]

    dau = filtered_sessions.groupby("date")["user_id"].nunique().reset_index(name="DAU")

    wau = []
    mau = []
    dates = sorted(filtered_sessions["date"].unique())

    for d in dates:
        d = pd.to_datetime(d).date()
        wau_count = filtered_sessions[
            (filtered_sessions["date"] >= d - pd.Timedelta(days=6)) &
            (filtered_sessions["date"] <= d)
        ]["user_id"].nunique()

        mau_count = filtered_sessions[
            (filtered_sessions["date"] >= d - pd.Timedelta(days=29)) &
            (filtered_sessions["date"] <= d)
        ]["user_id"].nunique()

        wau.append(wau_count)
        mau.append(mau_count)

    dau["WAU"] = wau
    dau["MAU"] = mau
    return dau

# ==== 5. Funnel calculation ====
def calculate_funnel(device):
    """Правильна воронка: тільки ті, хто зробив депозит → ті, хто зробив ставку"""
    registrations_users = get_device_users(device)

    deposit_users = set(
        transactions[
            (transactions["transaction_type"] == "deposit") &
            (transactions["user_id"].isin(registrations_users))
        ]["user_id"]
    )

    bet_users = set(
        bets[
            bets["user_id"].isin(deposit_users)
        ]["user_id"]
    )

    return len(registrations_users), len(deposit_users), len(bet_users)

# ==== 6. GGR by country ====
def ggr_by_country(device):
    """Розрахунок GGR по країнах"""
    if device == "all":
        dev_users = get_device_users("all")
        filtered_bets = bets[bets["user_id"].isin(dev_users)]
    else:
        dev_users = get_device_users(device)
        filtered_bets = bets[bets["user_id"].isin(dev_users)]

    bets_users = filtered_bets.merge(users, on="user_id", how="left")
    ggr_country = bets_users.groupby("country")["bet_amount"].sum().reset_index(name="GGR")

    def country_name(code):
        try:
            return pycountry.countries.get(alpha_2=code).name
        except:
            return code

    ggr_country["country"] = ggr_country["country"].apply(country_name)
    return ggr_country

# ==== 7. Dash app ====
app = Dash(__name__)
app.title = "Gaming Analytics Dashboard"

app.layout = html.Div(
    style={"backgroundColor": "#FAF6F1", "fontFamily": "Arial, sans-serif", "padding": "20px"},
    children=[
        html.Div(style={"maxWidth": "1600px", "margin": "0 auto"}, children=[
            html.H1("Gaming Analytics Dashboard", style={
                "textAlign": "center",
                "color": "#222",
                "fontSize": "clamp(20px, 3vw, 36px)",
                "marginBottom": "30px"
            }),

            html.Div([
                html.Label("Select Device Type", style={
                    "fontWeight": "bold",
                    "fontSize": "16px",
                    "marginRight": "10px"
                }),
                dcc.Dropdown(
                    id="device-filter",
                    options=[
                        {"label": "All Devices", "value": "all"},
                        {"label": "Mobile", "value": "mobile"},
                        {"label": "Desktop", "value": "desktop"}
                    ],
                    value="all",
                    clearable=False,
                    style={"width": "min(90%, 300px)"}
                )
            ], style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "center",
                "gap": "10px",
                "marginBottom": "30px"
            }),

            html.Div([
                html.Div([dcc.Graph(id="metrics-graph", config={"responsive": True})],
                         style={"flex": "1 1 48%", "minWidth": "300px"}),
                html.Div([dcc.Graph(id="funnel-graph", config={"responsive": True})],
                         style={"flex": "1 1 48%", "minWidth": "300px"})
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "20px",
                "justifyContent": "center",
                "marginBottom": "20px"
            }),

            html.Div([
                html.Div([dcc.Graph(id="geo-map", config={"responsive": True})],
                         style={"flex": "1 1 48%", "minWidth": "300px"}),
                html.Div([dcc.Graph(id="bar-chart", config={"responsive": True})],
                         style={"flex": "1 1 48%", "minWidth": "300px"})
            ], style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "20px",
                "justifyContent": "center"
            })
        ])
    ]
)

@app.callback(
    [Output("metrics-graph", "figure"),
     Output("funnel-graph", "figure"),
     Output("geo-map", "figure"),
     Output("bar-chart", "figure")],
    [Input("device-filter", "value")]
)
def update_dashboard(device):
    # Metrics
    metrics_df = calculate_metrics(device)
    fig_metrics = px.line(metrics_df, x="date", y=["DAU", "WAU", "MAU"], markers=True,
                          title=f"DAU / WAU / MAU — {device.capitalize()}")
    fig_metrics.update_layout(plot_bgcolor="#FAF6F1", paper_bgcolor="#FAF6F1", font_color="#222")

    # Funnel
    reg, dep, bet_cnt = calculate_funnel(device)
    funnel_df = pd.DataFrame({
        "stage": ["Registration", "Deposit", "Bet"],
        "value": [reg, dep, bet_cnt]
    })
    fig_funnel = go.Figure(go.Funnel(
        y=funnel_df["stage"], x=funnel_df["value"],
        textinfo="value+percent previous",
        marker={"color": ["#7DD1C0", "#6FB0A9", "#5D9A99"]}
    ))
    fig_funnel.update_layout(plot_bgcolor="#FAF6F1", paper_bgcolor="#FAF6F1", font_color="#222")

    # GGR map
    ggr_country_df = ggr_by_country(device)
    fig_geo = px.choropleth(
        ggr_country_df, locations="country", locationmode="country names",
        color="GGR", color_continuous_scale="Blues", title="GGR by Country"
    )
    fig_geo.update_layout(plot_bgcolor="#FAF6F1", paper_bgcolor="#FAF6F1", font_color="#222")

    # Bar chart
    fig_bar = px.bar(
        ggr_country_df.sort_values("GGR", ascending=False),
        x="GGR", y="country", orientation="h", title="Top Countries by GGR"
    )
    fig_bar.update_layout(plot_bgcolor="#FAF6F1", paper_bgcolor="#FAF6F1", font_color="#222")

    return fig_metrics, fig_funnel, fig_geo, fig_bar


if __name__ == "__main__":
    app.run(debug=True)
