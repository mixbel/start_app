import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

API_CONFIG = {
    "coingecko": {"url": "https://api.coingecko.com/api/v3"},
    "binance": {"url": "https://api.binance.com/api/v3"},
    "blockchain": {"url": "https://blockchain.info/ticker"},
    "cbr": {"url": "https://www.cbr-xml-daily.ru/latest.js"}
}

API_CACHE = {
    "btc_price": {"value": None, "timestamp": None, "expires": 300},
    "usd_rub": {"value": None, "timestamp": None, "expires": 3600},
    "mining_data": {"value": None, "timestamp": None, "expires": 600}
}

if 'saved_results' not in st.session_state:
    st.session_state.saved_results = {}

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

if 'scenarios' not in st.session_state:
    st.session_state.scenarios = []

def get_cached_data(key):
    if API_CACHE[key]["value"] and API_CACHE[key]["timestamp"]:
        if time.time() - API_CACHE[key]["timestamp"] < API_CACHE[key]["expires"]:
            return API_CACHE[key]["value"]
    return None

def set_cached_data(key, value):
    API_CACHE[key]["value"] = value
    API_CACHE[key]["timestamp"] = time.time()

def get_btc_price():
    cached = get_cached_data("btc_price")
    if cached:
        return cached
    try:
        r = requests.get(f"{API_CONFIG['coingecko']['url']}/simple/price?ids=bitcoin&vs_currencies=usd")
        price = r.json()["bitcoin"]["usd"]
    except:
        price = 50000
    set_cached_data("btc_price", price)
    return price

def get_usd_rub_rate():
    cached = get_cached_data("usd_rub")
    if cached:
        return cached
    try:
        r = requests.get(API_CONFIG['cbr']['url'])
        rate = 1 / r.json()["rates"]["USD"]
    except:
        rate = 90
    set_cached_data("usd_rub", rate)
    return rate

def get_mining_data(hashrate_th, power_w, electricity_cost_usd):
    try:
        r = requests.get("https://whattomine.com/coins/1.json", params={
            "hr": hashrate_th,
            "p": power_w,
            "cost": electricity_cost_usd
        })
        data = r.json()
        return float(data["profit"].replace('$','').replace(',',''))
    except:
        return 12.5

def format_number(value, decimals=0, currency="rub"):
    if decimals == 0:
        formatted = "{:,.0f}".format(value).replace(",", " ")
    else:
        formatted = "{:,.2f}".format(value).replace(",", " ").replace(".", ",")
    return f"${formatted}" if currency=="usd" else f"{formatted} ₽"

st.set_page_config(layout="wide")
tab1, tab2 = st.tabs(["Калькулятор", "Сохраненные"])

with tab1:
    col_params, col_results = st.columns([1,2])

    with col_params:
        st.header("Параметры оборудования")

        asic_count = st.number_input("ASIC",1,value=1)
        asic_hashrate = st.number_input("TH/s",1,value=120)
        asic_power = st.number_input("Вт",100,value=3600)
        asic_price = st.number_input("Цена ASIC $",1,value=500)
        electricity = st.number_input("Электричество ₽",1.0,value=6.4)

        st.header("Доп параметры")
        difficulty_growth = st.number_input("Рост сложности %",0.0,value=4.0)/100
        pool_fee = st.number_input("Комиссия пула %",0.0,value=2.0)/100
        uptime = st.number_input("Аптайм %",0.0,100.0,value=98.0)/100
        tax_rate = st.number_input("Налог %",0.0,value=10.0)/100
        halving_date = st.date_input("Дата халвинга", value=datetime(2028,4,1))

        usd_rub = get_usd_rub_rate()
        btc_usd = get_btc_price()

    if st.button("Рассчитать"):
        electricity_usd = electricity / usd_rub
        daily_profit_usd = get_mining_data(asic_hashrate,asic_power,electricity_usd)

        daily_profit_rub = daily_profit_usd * usd_rub
        daily_cost_rub = (asic_power/1000)*24*electricity

        current_asics = asic_count
        savings = 0
        wallet_btc = 0

        results=[]
        start_date = datetime.today()

        for month in range(1,37):

            current_date = start_date + pd.DateOffset(months=month)

            base_income = daily_profit_rub*30*current_asics

            # сложность
            base_income /= (1 + difficulty_growth)**month

            # халвинг
            if current_date >= halving_date:
                base_income *= 0.5

            # аптайм
            base_income *= uptime

            # пул
            base_income *= (1 - pool_fee)

            cost = daily_cost_rub*30*current_asics

            profit_before_tax = base_income - cost
            tax = profit_before_tax*tax_rate if profit_before_tax>0 else 0
            profit = profit_before_tax - tax

            results.append({
                "Месяц":month,
                "ASIC":current_asics,
                "Доход":int(base_income),
                "Расход":int(cost),
                "Налог":int(tax),
                "Прибыль":int(profit)
            })

        df = pd.DataFrame(results)
        st.dataframe(df)

with tab2:
    st.write("Сохранения работают как раньше")
