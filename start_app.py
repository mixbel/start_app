import streamlit as st
import pandas as pd
import requests
import time
import openpyxl
from io import BytesIO
from datetime import datetime, timedelta

# Настройки API
API_CONFIG = {
    "coingecko": {
        "url": "https://api.coingecko.com/api/v3",
        "rate_limit": 10
    },
    "binance": {
        "url": "https://api.binance.com/api/v3",
        "rate_limit": 1200
    },
    "blockchain": {
        "url": "https://blockchain.info/ticker",
        "rate_limit": 60
    },
    "cbr": {
        "url": "https://www.cbr-xml-daily.ru/latest.js",
        "rate_limit": 60
    }
}

# Глобальный кэш для хранения данных
API_CACHE = {
    "btc_price": {"value": None, "timestamp": None, "expires": 300},
    "usd_rub": {"value": None, "timestamp": None, "expires": 3600},
    "mining_data": {"value": None, "timestamp": None, "expires": 600}
}

# Инициализация session_state
if 'saved_results' not in st.session_state:
    st.session_state.saved_results = {}

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

if 'scenarios' not in st.session_state:
    st.session_state.scenarios = []

# --- Функции для работы с API ---
def get_cached_data(key):
    if API_CACHE[key]["value"] and API_CACHE[key]["timestamp"]:
        elapsed = time.time() - API_CACHE[key]["timestamp"]
        if elapsed < API_CACHE[key]["expires"]:
            return API_CACHE[key]["value"]
    return None

def set_cached_data(key, value):
    API_CACHE[key]["value"] = value
    API_CACHE[key]["timestamp"] = time.time()

def fetch_with_fallback(urls, parse_funcs):
    for url, parse_func in zip(urls, parse_funcs):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            if response.status_code == 200:
                data = parse_func(response.json())
                if data is not None:
                    return data
        except:
            continue
    return None

def get_btc_price():
    cached = get_cached_data("btc_price")
    if cached:
        return cached
    
    sources = [
        f"{API_CONFIG['coingecko']['url']}/simple/price?ids=bitcoin&vs_currencies=usd",
        f"{API_CONFIG['binance']['url']}/ticker/price?symbol=BTCUSDT",
        API_CONFIG['blockchain']['url']
    ]
    
    parse_funcs = [
        lambda x: x["bitcoin"]["usd"],
        lambda x: float(x["price"]),
        lambda x: x["USD"]["last"]
    ]
    
    price = fetch_with_fallback(sources, parse_funcs)
    
    if price is None and API_CACHE["btc_price"]["value"]:
        return API_CACHE["btc_price"]["value"]
    
    price = price or 50000
    set_cached_data("btc_price", price)
    return price

def get_usd_rub_rate():
    cached = get_cached_data("usd_rub")
    if cached:
        return cached
    
    sources = [
        f"{API_CONFIG['coingecko']['url']}/simple/price?ids=bitcoin&vs_currencies=usd,rub",
        API_CONFIG['cbr']['url'],
        f"{API_CONFIG['binance']['url']}/ticker/price?symbol=USDTRUB"
    ]
    
    parse_funcs = [
        lambda x: x["bitcoin"]["rub"] / x["bitcoin"]["usd"],
        lambda x: 1 / x["rates"]["USD"],
        lambda x: float(x["price"])
    ]
    
    rate = fetch_with_fallback(sources, parse_funcs)
    
    if rate is None and API_CACHE["usd_rub"]["value"]:
        return API_CACHE["usd_rub"]["value"]
    
    rate = rate or 90
    set_cached_data("usd_rub", rate)
    return rate

def get_mining_data_with_retry(hashrate_th, power_w, electricity_cost_usd, retries=3):
    for attempt in range(retries):
        try:
            params = {
                "hr": hashrate_th,
                "p": power_w,
                "cost": electricity_cost_usd,
                "fee": 0,
                "commit": "Calculate"
            }
            response = requests.get("https://whattomine.com/coins/1.json", 
                                 params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                result = {
                    "daily_profit": float(data["profit"].replace('$', '').replace(',', '')),
                    "daily_revenue": float(data["revenue"].replace('$', '').replace(',', ''))
                }
                return result
        except Exception as e:
            if attempt == retries - 1:
                return {
                    "daily_profit": 12.50,
                    "daily_revenue": 18.00
                }
            time.sleep(1 * (attempt + 1))
    
    return {
        "daily_profit": 12.50,
        "daily_revenue": 18.00
    }

# --- Функции для работы со сценариями ---
def add_scenario():
    if not st.session_state.scenarios:
        st.session_state.scenarios.append({
            "start": 1,
            "end": 12,
            "reinvest": 50,
            "wallet": 10
        })
    else:
        last_end = st.session_state.scenarios[-1]["end"]
        st.session_state.scenarios.append({
            "start": last_end + 1,
            "end": last_end + 12,
            "reinvest": 50,
            "wallet": 10
        })

def remove_scenario(index):
    st.session_state.scenarios.pop(index)
    for i in range(len(st.session_state.scenarios)):
        if i == 0:
            st.session_state.scenarios[i]["start"] = 1
        else:
            st.session_state.scenarios[i]["start"] = st.session_state.scenarios[i-1]["end"] + 1
        st.session_state.scenarios[i]["end"] = st.session_state.scenarios[i]["start"] + 11

# --- Функция для экспорта в Excel ---
def export_to_excel(df):
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Результаты майнинга', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Результаты майнинга']
        
        for col in range(1, len(df.columns) + 1):
            cell = worksheet.cell(row=1, column=col)
            cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            cell.fill = openpyxl.styles.PatternFill(start_color="FF5757", end_color="FF5757", fill_type="solid")
            cell.alignment = openpyxl.styles.Alignment(horizontal="center")
        
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output

# --- Основные функции калькулятора ---
def format_number(value, decimals=0, currency="rub"):
    if pd.isna(value) or value == 0:
        return "0"
    try:
        if decimals == 0:
            formatted = "{:,.0f}".format(value).replace(",", " ")
        else:
            formatted = "{:,.{}f}".format(value, decimals).replace(",", " ").replace(".", ",")
        
        if currency == "usd":
            return f"${formatted}"
        elif currency == "rub":
            return f"{formatted} ₽"
        return formatted
    except:
        return str(value)

# --- Интерфейс ---
st.set_page_config(
    page_title="Калькулятор Gazminer",
    page_icon="⛏️",
    layout="wide"
)

# ========== ЗАГОЛОВОК С ЛОГОТИПОМ ==========
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("89120564-6.png", width=100)
    st.markdown("<h1 style='text-align: center;'>Калькулятор от Gazminer</h1>", unsafe_allow_html=True)
st.markdown("---")
# ===========================================

# ========== КАСТОМНЫЙ ДИЗАЙН ==========
st.markdown("""
<style>
    .stApp { background-color: #1a1a1a !important; }
    .stMarkdown, .stText, .stNumberInput label, .stCheckbox label, .stSelectbox label, .stDateInput label { color: white !important; }
    h1 { color: white !important; }
    h2, h3, .stHeader { color: #2cb1c3 !important; }
    .stButton button { background-color: #ff5757 !important; color: white !important; border: none !important; border-radius: 8px !important; padding: 8px 16px !important; font-weight: bold !important; }
    .stButton button:hover { background-color: #ff3333 !important; }
    .stNumberInput input, .stTextInput input, .stDateInput input, .stSelectbox select { border: 2px solid #2cb1c3 !important; border-radius: 8px !important; background-color: #2a2a2a !important; color: white !important; }
    [data-testid="stMetric"] { background-color: #2a2a2a !important; border-radius: 10px !important; padding: 10px !important; border-left: 4px solid #ff5757 !important; }
    [data-testid="stMetricLabel"] { color: white !important; }
    [data-testid="stMetricValue"] { color: #ff5757 !important; }
    .stAlert { background-color: #2a2a2a !important; border-left-color: #ff5757 !important; color: white !important; }
    .stContainer { background-color: #2a2a2a !important; border-radius: 12px !important; padding: 15px !important; border: 1px solid #2cb1c3 !important; }
    .stTabs [data-baseweb="tab"] { background-color: #2a2a2a !important; border-radius: 8px !important; padding: 8px 16px !important; color: white !important; }
    .stTabs [aria-selected="true"] { background-color: #ff5757 !important; color: white !important; }
    div[data-testid="stDataFrame"] { background-color: #2a2a2a !important; }
    div[data-testid="stDataFrame"] tbody tr td { background-color: #2a2a2a !important; color: white !important; }
    div[data-testid="stDataFrame"] thead tr th { background-color: #ff5757 !important; color: white !important; }
</style>
""", unsafe_allow_html=True)
# ===================================================

tab1, tab2 = st.tabs(["Калькулятор", "Сохраненные результаты"])

with tab1:
    col_params, col_results = st.columns([1, 2], gap="large")
    
    with col_params:
        st.header("Параметры оборудования")
        asic_count = st.number_input("Количество ASIC", min_value=1, value=1, key="asic_count")
        asic_hashrate = st.number_input("Хешрейт 1 ASIC (TH/s)", min_value=1, value=120, key="asic_hashrate")
        asic_power = st.number_input("Потребление 1 ASIC (Вт)", min_value=100, value=3600, key="asic_power")
        asic_price = st.number_input("Стоимость 1 ASIC ($)", min_value=1, value=500, key="asic_price")
        electricity = st.number_input("Электричество (руб/кВт·ч)", min_value=1.0, value=6.4, key="electricity")
        
        st.header("Дополнительные параметры")
        difficulty_growth = st.number_input("Рост сложности (% в месяц)", min_value=0.0, max_value=50.0, value=3.0, step=0.5, key="difficulty_growth") / 100
        pool_fee = st.number_input("Комиссия пула (%)", min_value=0.0, max_value=10.0, value=2.0, step=0.5, key="pool_fee") / 100
        tax_rate = st.number_input("Налог на прибыль (%)", min_value=0.0, max_value=50.0, value=13.0, step=1.0, key="tax_rate") / 100
        uptime = st.number_input("Аптайм (%)", min_value=0.0, max_value=100.0, value=97.0, step=1.0, key="uptime") / 100
        
        st.subheader("Халвинг Bitcoin")
        halving_date = st.date_input(
            "Дата следующего халвинга",
            value=datetime(2028, 4, 1),
            min_value=datetime.today(),
            help="После этой даты награда за блок уменьшится в 2 раза",
            key="halving_date"
        )
        
        st.subheader("Прогнозы на конец расчетного периода")
        forecast_btc_price = st.number_input(
            "Прогноз цены Биткоина (тыс. $)",
            min_value=1.0,
            value=150.0,
            step=5.0,
            key="forecast_btc_price",
            help="Укажите прогнозируемую цену BTC в тысячах долларов (например, 150 = 150 000 $)"
        )
        
        forecast_usd_rub = st.number_input(
            "Прогноз курса USD/RUB",
            min_value=1.0,
            value=80.0,
            step=5.0,
            key="forecast_usd_rub",
            help="Укажите прогнозируемый курс доллара к рублю"
        )
        
        today = datetime.today().date()
        if halving_date > today:
            months_to_halving = (halving_date.year - today.year) * 12 + (halving_date.month - today.month)
            if months_to_halving <= 1:
                st.info(f"Халвинг наступит через {months_to_halving} месяц(ев)")
            else:
                st.info(f"Халвинг наступит через {months_to_halving} месяцев")
        elif halving_date == today:
            st.warning("Халвинг наступает сегодня!")
        else:
            st.warning("Выбранная дата уже прошла, халвинг уже должен был произойти")
        
        show_in_usd = st.checkbox("Показать расчеты в $", value=False, key="show_in_usd")
        
        if st.button("Обновить курсы"):
            for key in API_CACHE:
                API_CACHE[key]["value"] = None
                API_CACHE[key]["timestamp"] = None
            st.success("Курсы обновлены!")
        
        usd_rub = get_usd_rub_rate()
        btc_usd = get_btc_price()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Курс USD/RUB", f"{format_number(usd_rub, 2)} ₽")
        with col2:
            st.metric("Цена BTC", f"{format_number(btc_usd, 2)} $")

        st.header("Сценарии реинвестирования")
        if not st.session_state.scenarios:
            add_scenario()

        for i, scenario in enumerate(st.session_state.scenarios):
            with st.container(border=True):
                cols = st.columns(2)
                with cols[0]:
                    start = st.number_input("С (месяц)", min_value=1, value=scenario['start'], 
                                          key=f"start_{i}", step=1)
                with cols[1]:
                    end = st.number_input("По (месяц)", min_value=start, value=scenario['end'], 
                                        key=f"end_{i}", step=1)
                
                reinvest = st.slider("Реинвестиции %", 0, 100, scenario['reinvest'], 
                                   key=f"reinvest_{i}")
                wallet = st.slider("В кошелек % из реинвеста", 0, 100, scenario['wallet'], 
                                 key=f"wallet_{i}")
                
                if st.button("Удалить", key=f"remove_{i}"):
                    remove_scenario(i)
                    st.rerun()
                
                st.session_state.scenarios[i] = {
                    "start": start,
                    "end": end,
                    "reinvest": reinvest,
                    "wallet": wallet
                }

        if st.button("Добавить период"):
            add_scenario()
            st.rerun()

    if st.button("Рассчитать", type="primary", use_container_width=True, key="calculate_btn"):
        with st.spinner("Выполняю расчет..."):
            usd_rub = get_usd_rub_rate()
            btc_usd = get_btc_price()
            electricity_usd = electricity / usd_rub
            
            forecast_btc_price_usd = forecast_btc_price * 1000
            forecast_usd_rub_rate = forecast_usd_rub
            
            mining_data_per_asic = get_mining_data_with_retry(
                asic_hashrate,
                asic_power,
                electricity_usd
            )
            
            daily_revenue_per_asic_usd = mining_data_per_asic["daily_revenue"]
            daily_profit_per_asic_usd = mining_data_per_asic["daily_profit"]
            daily_cost_per_asic_usd = daily_revenue_per_asic_usd - daily_profit_per_asic_usd
            
            daily_revenue_per_asic_rub = daily_revenue_per_asic_usd * usd_rub
            daily_cost_per_asic_rub = daily_cost_per_asic_usd * usd_rub
            
            current_asics = asic_count
            savings = 0
            wallet_btc = 0
            results = []
            
            total_investment = asic_count * asic_price * usd_rub
            total_investment_usd = asic_count * asic_price
            cumulative_profit_before_tax = 0
            cumulative_net_profit = 0
            break_even_month = None
            clean_break_even_month = None
            
            total_months = max(s["end"] for s in st.session_state.scenarios) if st.session_state.scenarios else 36
            
            halving_datetime = datetime.combine(halving_date, datetime.min.time())
            start_date = datetime.today()
            
            for month in range(1, total_months + 1):
                active_scenario = None
                for scenario in st.session_state.scenarios:
                    if scenario["start"] <= month <= scenario["end"]:
                        active_scenario = scenario
                        break
                
                if not active_scenario:
                    continue
                
                reinvest_percent = active_scenario["reinvest"]
                wallet_percent = active_scenario["wallet"]
                
                current_date = start_date + pd.DateOffset(months=month)
                
                revenue_full = daily_revenue_per_asic_rub * 30 * current_asics
                
                difficulty_multiplier = (1 + difficulty_growth) ** (month - 1)
                revenue_full = revenue_full / difficulty_multiplier if difficulty_multiplier > 0 else revenue_full
                
                if current_date >= halving_datetime:
                    revenue_full = revenue_full * 0.5
                
                revenue = revenue_full * uptime
                lost_revenue = revenue_full - revenue
                
                pool_fee_amount = revenue * pool_fee
                electricity_cost = daily_cost_per_asic_rub * 30 * current_asics
                total_costs = pool_fee_amount + electricity_cost
                
                profit_before_tax = revenue - total_costs
                
                if profit_before_tax > 0:
                    tax = profit_before_tax * tax_rate
                    net_profit = profit_before_tax - tax
                else:
                    tax = 0
                    net_profit = profit_before_tax
                
                to_reinvest = net_profit * (reinvest_percent / 100)
                salary = net_profit - to_reinvest
                to_wallet = to_reinvest * (wallet_percent / 100)
                to_asics = to_reinvest - to_wallet
                
                savings += to_asics
                btc_amount = to_wallet / usd_rub / btc_usd
                wallet_btc += btc_amount
                
                new_asics = int(savings // (asic_price * usd_rub))
                if new_asics > 0:
                    current_asics += new_asics
                    savings -= new_asics * asic_price * usd_rub
                    daily_revenue_per_asic_rub = (mining_data_per_asic["daily_revenue"] * usd_rub)
                    daily_cost_per_asic_rub = (daily_revenue_per_asic_usd - daily_profit_per_asic_usd) * usd_rub
                
                cumulative_profit_before_tax += profit_before_tax
                investment_for_break_even = total_investment_usd if show_in_usd else total_investment
                if cumulative_profit_before_tax >= investment_for_break_even and break_even_month is None:
                    break_even_month = month
                
                cumulative_net_profit += net_profit
                if cumulative_net_profit >= investment_for_break_even and clean_break_even_month is None:
                    clean_break_even_month = month
                
                if show_in_usd:
                    revenue_usd = revenue / usd_rub
                    lost_revenue_usd = lost_revenue / usd_rub
                    pool_fee_usd = pool_fee_amount / usd_rub
                    electricity_usd_calc = electricity_cost / usd_rub
                    total_costs_usd = total_costs / usd_rub
                    profit_before_tax_usd = profit_before_tax / usd_rub
                    tax_usd = tax / usd_rub
                    net_profit_usd = net_profit / usd_rub
                    salary_usd = salary / usd_rub
                    to_reinvest_usd = to_reinvest / usd_rub
                    to_wallet_usd = to_wallet / usd_rub
                    savings_usd = savings / usd_rub
                    
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доход": int(revenue_usd),
                        "Комиссия пула": int(pool_fee_usd),
                        "Электрика": int(electricity_usd_calc),
                        "Расходы": int(total_costs_usd),
                        "Прибыль": int(profit_before_tax_usd),
                        "Налог": int(tax_usd),
                        "Потерянный доход": int(lost_revenue_usd),
                        "Чистая прибыль": int(net_profit_usd),
                        "Зарплата": int(salary_usd),
                        "Реинвест": int(to_reinvest_usd),
                        "В кошелек": int(to_wallet_usd),
                        "Накопления": int(savings_usd),
                        "Кошелек BTC": f"{wallet_btc:.8f} BTC",
                        "Кошелек USD": format_number(wallet_btc * btc_usd, 2, 'usd')
                    })
                else:
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доход": int(revenue),
                        "Комиссия пула": int(pool_fee_amount),
                        "Электрика": int(electricity_cost),
                        "Расходы": int(total_costs),
                        "Прибыль": int(profit_before_tax),
                        "Налог": int(tax),
                        "Потерянный доход": int(lost_revenue),
                        "Чистая прибыль": int(net_profit),
                        "Зарплата": int(salary),
                        "Реинвест": int(to_reinvest),
                        "В кошелек": int(to_wallet),
                        "Накопления": int(savings),
                        "Кошелек BTC": f"{wallet_btc:.8f} BTC",
                        "Кошелек RUB": format_number(wallet_btc * btc_usd * usd_rub, 0, 'rub')
                    })
            
            if results:
                last_month_btc = wallet_btc
                forecast_value_usd = last_month_btc * forecast_btc_price_usd
                forecast_value_rub = forecast_value_usd * forecast_usd_rub_rate
                
                if show_in_usd:
                    results[-1]["Продажа по прогнозу"] = format_number(forecast_value_usd, 0, 'usd')
                else:
                    results[-1]["Продажа по прогнозу"] = format_number(forecast_value_rub, 0, 'rub')
            
            df = pd.DataFrame(results)
            st.session_state.current_results = df
            st.rerun()

    with col_results:
        if st.session_state.current_results is not None:
            df = st.session_state.current_results.copy()
            usd_rub = get_usd_rub_rate()
            btc_usd = get_btc_price()
            
            initial_investment = asic_count * asic_price * (usd_rub if not show_in_usd else 1)
            
            cumulative_net = df['Чистая прибыль'].cumsum()
            clean_break_even_month = None
            for _, row in df.iterrows():
                if cumulative_net[row['Месяц']-1] >= initial_investment:
                    clean_break_even_month = row['Месяц']
                    break
            
            cumulative_profit = df['Прибыль'].cumsum()
            dirty_break_even_month = None
            for _, row in df.iterrows():
                if cumulative_profit[row['Месяц']-1] >= initial_investment:
                    dirty_break_even_month = row['Месяц']
                    break
            
            summary_data = {
                "Показатель": [
                    "Первоначальные инвестиции", 
                    "Окупаемость по чистой прибыли (мес)", 
                    "Окупаемость по прибыли до налога (мес)",
                    "Общий доход",
                    "Общая комиссия пула",
                    "Общие расходы на электрику",
                    "Общие расходы",
                    "Прибыль до налога",
                    "Общий налог",
                    "Общий потерянный доход",
                    "Чистая прибыль",
                    "Финальное кол-во ASIC",
                    "Накоплено BTC"
                ],
                "Значение": [
                    format_number(initial_investment, 0, "usd" if show_in_usd else "rub"),
                    str(clean_break_even_month) if clean_break_even_month else "Не окупилось",
                    str(dirty_break_even_month) if dirty_break_even_month else "Не окупилось",
                    format_number(df['Доход'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Комиссия пула'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Электрика'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Расходы'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Прибыль'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Налог'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Потерянный доход'].sum(), 0, "usd" if show_in_usd else "rub"),
                    format_number(df['Чистая прибыль'].sum(), 0, "usd" if show_in_usd else "rub"),
                    f"{df.iloc[-1]['ASIC']} шт.",
                    df.iloc[-1]['Кошелек BTC']
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df.style.hide(axis="index"), hide_index=True, use_container_width=True)
            
            display_columns = [
                "Месяц", "ASIC", "Доход", "Комиссия пула", "Электрика", "Расходы", 
                "Прибыль", "Налог", "Потерянный доход", "Чистая прибыль", 
                "Зарплата", "Реинвест", "В кошелек", "Накопления", "Кошелек BTC"
            ]
            if show_in_usd:
                display_columns.append("Кошелек USD")
            else:
                display_columns.append("Кошелек RUB")
            
            if "Продажа по прогнозу" in df.columns:
                display_columns.append("Продажа по прогнозу")
            
            formatted_df = df[display_columns].copy()
            for col in ["Доход", "Комиссия пула", "Электрика", "Расходы", "Прибыль", 
                       "Налог", "Потерянный доход", "Чистая прибыль", "Зарплата", 
                       "Реинвест", "В кошелек", "Накопления"]:
                if col in formatted_df.columns:
                    formatted_df[col] = formatted_df[col].apply(lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"))
            
            st.dataframe(formatted_df, hide_index=True, use_container_width=True, height=700)
            
            col_export1, col_export2, col_export3 = st.columns([1, 2, 1])
            with col_export2:
                if st.button("Скачать результаты в Excel", type="secondary", use_container_width=True):
                    with st.spinner("Подготавливаю файл..."):
                        export_df = df[display_columns].copy()
                        excel_file = export_to_excel(export_df)
                        st.download_button(
                            label="Скачать Excel файл",
                            data=excel_file,
                            file_name=f"mining_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
            
            with st.form("save_form"):
                result_name = st.text_input("Название сохранения", 
                                          value=f"Результат {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                if st.form_submit_button("Сохранить результаты"):
                    if result_name.strip():
                        if result_name in st.session_state.saved_results:
                            st.error("Результат с таким названием уже существует!")
                        else:
                            st.session_state.saved_results[result_name] = {
                                "timestamp": datetime.now().isoformat(),
                                "data": st.session_state.current_results.to_dict('records'),
                                "summary": summary_data,
                                "params": {
                                    "asic_count": asic_count,
                                    "asic_hashrate": asic_hashrate,
                                    "asic_power": asic_power,
                                    "asic_price": asic_price,
                                    "electricity": electricity,
                                    "difficulty_growth": difficulty_growth,
                                    "pool_fee": pool_fee,
                                    "tax_rate": tax_rate,
                                    "uptime": uptime,
                                    "halving_date": halving_date.isoformat(),
                                    "forecast_btc_price": forecast_btc_price,
                                    "forecast_usd_rub": forecast_usd_rub,
                                    "show_in_usd": show_in_usd,
                                    "usd_rub_rate": usd_rub,
                                    "btc_price_usd": btc_usd,
                                    "scenarios": st.session_state.scenarios.copy()
                                }
                            }
                            st.success(f"Результаты сохранены под названием: {result_name}")
                            st.rerun()
                    else:
                        st.error("Введите название для сохранения")

with tab2:
    st.title("Сохраненные результаты")
    
    if not st.session_state.get('saved_results', {}):
        st.info("Нет сохраненных результатов")
    else:
        saved_results_copy = st.session_state.saved_results.copy()
        
        for name, data in saved_results_copy.items():
            with st.expander(f"{name} ({data['timestamp']})"):
                st.write("Параметры расчета:")
                st.json(data["params"])
                
                if "summary" in data:
                    st.write("Сводные данные:")
                    summary_df = pd.DataFrame(data["summary"])
                    st.dataframe(summary_df.style.hide(axis="index"), hide_index=True, use_container_width=True)
                
                df = pd.DataFrame(data["data"])
                show_in_usd_saved = data["params"].get("show_in_usd", False)
                
                display_columns = [
                    "Месяц", "ASIC", "Доход", "Комиссия пула", "Электрика", "Расходы", 
                    "Прибыль", "Налог", "Потерянный доход", "Чистая прибыль", 
                    "Зарплата", "Реинвест", "В кошелек", "Накопления", "Кошелек BTC"
                ]
                if show_in_usd_saved and "Кошелек USD" in df.columns:
                    display_columns.append("Кошелек USD")
                elif not show_in_usd_saved and "Кошелек RUB" in df.columns:
                    display_columns.append("Кошелек RUB")
                
                if "Продажа по прогнозу" in df.columns:
                    display_columns.append("Продажа по прогнозу")
                
                formatted_df = df[display_columns].copy()
                for col in ["Доход", "Комиссия пула", "Электрика", "Расходы", "Прибыль", 
                           "Налог", "Потерянный доход", "Чистая прибыль", "Зарплата", 
                           "Реинвест", "В кошелек", "Накопления"]:
                    if col in formatted_df.columns:
                        formatted_df[col] = formatted_df[col].apply(lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"))
                
                st.dataframe(formatted_df, hide_index=True, use_container_width=True)
                
                if st.button(f"Удалить {name}", key=f"delete_{name}"):
                    del st.session_state.saved_results[name]
                    st.rerun()
