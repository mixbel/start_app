import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# Настройки API
API_CONFIG = {
    "coingecko": {"url": "https://api.coingecko.com/api/v3", "rate_limit": 10},
    "binance": {"url": "https://api.binance.com/api/v3", "rate_limit": 1200},
    "blockchain": {"url": "https://blockchain.info/ticker", "rate_limit": 60},
    "cbr": {"url": "https://www.cbr-xml-daily.ru/latest.js", "rate_limit": 60}
}

# Кэш данных
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
if 'show_in_usd' not in st.session_state:
    st.session_state.show_in_usd = False

# --- Функции API ---
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
    if cached: return cached
    
    sources = [
        f"{API_CONFIG['coingecko']['url']}/simple/price?ids=bitcoin&vs_currencies=usd",
        f"{API_CONFIG['binance']['url']}/ticker/price?symbol=BTCUSDT",
        API_CONFIG['blockchain']['url']
    ]
    
    price = fetch_with_fallback(sources, [
        lambda x: x["bitcoin"]["usd"],
        lambda x: float(x["price"]),
        lambda x: x["USD"]["last"]
    ])
    
    price = price or 50000
    set_cached_data("btc_price", price)
    return price

def get_usd_rub_rate():
    cached = get_cached_data("usd_rub")
    if cached: return cached
    
    sources = [
        f"{API_CONFIG['coingecko']['url']}/simple/price?ids=bitcoin&vs_currencies=usd,rub",
        API_CONFIG['cbr']['url'],
        f"{API_CONFIG['binance']['url']}/ticker/price?symbol=USDTRUB"
    ]
    
    rate = fetch_with_fallback(sources, [
        lambda x: x["bitcoin"]["rub"] / x["bitcoin"]["usd"],
        lambda x: 1 / x["rates"]["USD"],
        lambda x: float(x["price"])
    ])
    
    rate = rate or 90
    set_cached_data("usd_rub", rate)
    return rate

def get_mining_data_with_retry(hashrate_th, power_w, electricity_cost_usd, retries=3):
    cached = get_cached_data("mining_data")
    if cached: return cached
    
    for attempt in range(retries):
        try:
            params = {
                "hr": hashrate_th,
                "p": power_w,
                "cost": electricity_cost_usd,
                "fee": 1.0,
                "commit": "Calculate"
            }
            response = requests.get("https://whattomine.com/coins/1.json", params=params, timeout=10)
            data = response.json()
            result = {
                "daily_revenue": float(data["revenue"].replace('$', '').replace(',', '')),
                "difficulty": int(data["difficulty"]),
                "difficulty_change": float(data["difficulty24"].replace('%', '')) / 100
            }
            set_cached_data("mining_data", result)
            return result
        except:
            if attempt == retries - 1:
                return {
                    "daily_revenue": 18.00,
                    "difficulty": 82_000_000_000,
                    "difficulty_change": 0.05
                }
            time.sleep(1 * (attempt + 1))

# --- Функции калькулятора ---
def format_number(value, decimals=0, currency="rub"):
    if pd.isna(value) or value == 0: return "0"
    try:
        if decimals == 0:
            formatted = "{:,.0f}".format(value).replace(",", " ")
        else:
            formatted = "{:,.{}f}".format(value, decimals).replace(",", " ").replace(".", ",")
        
        if currency == "usd": return f"${formatted}"
        elif currency == "rub": return f"{formatted} ₽"
        return formatted
    except:
        return str(value)

def add_scenario():
    if not st.session_state.scenarios:
        st.session_state.scenarios.append({"start": 1, "end": 12, "reinvest": 50, "wallet": 10})
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

def generate_ai_analysis(selected_names):
    if len(selected_names) < 2: return "❌ Выберите минимум 2 результата"
    
    raw_data = []
    for name in selected_names:
        data = st.session_state.saved_results[name]
        df = pd.DataFrame(data["data"])
        raw_data.append({
            "name": name,
            "total_profit": df["Прибыль"].sum(),
            "final_asics": df["ASIC"].iloc[-1],
            "months": len(df),
            "reinvest": data["params"].get("scenarios", [{}])[0].get("reinvest", 50),
            "electricity_cost": data["params"]["electricity"]
        })
    
    analysis = "### 🧠 DeepSeek AI Analysis\n\n"
    
    # Сравнение прибыли
    max_profit = max(raw_data, key=lambda x: x["total_profit"])
    min_profit = min(raw_data, key=lambda x: x["total_profit"])
    profit_diff = max_profit["total_profit"] - min_profit["total_profit"]
    
    analysis += f"🔍 **Прибыль**: Лучший результат у '{max_profit['name']}' ({format_number(max_profit['total_profit'], 0, 'rub')}). "
    analysis += f"Разница: {format_number(profit_diff, 0, 'rub')} ({profit_diff/min_profit['total_profit']:.0%})\n\n"
    
    # Анализ стратегии
    analysis += "💡 **Стратегия**:\n"
    best_reinvest = max(raw_data, key=lambda x: x["reinvest"])
    if best_reinvest["reinvest"] > 70:
        analysis += f"- Высокий реинвест ({best_reinvest['reinvest']}%) даёт больше ASIC ({best_reinvest['final_asics']} шт.)\n"
    else:
        analysis += f"- Реинвест {best_reinvest['reinvest']}% можно увеличить для ускорения роста фермы\n"
    
    # Риски
    analysis += "⚠️ **Риски**:\n"
    if any(d["electricity_cost"] > 7 for d in raw_data):
        analysis += "- Высокая стоимость электричества снижает маржу\n"
    if max(d["months"] for d in raw_data) > 12:
        analysis += "- Долгий срок окупаемости (>12 мес) чувствителен к цене BTC\n"
    
    return analysis

# --- Интерфейс ---
st.set_page_config(page_title="Калькулятор майнинга PRO", page_icon="⛏️", layout="wide")
tab1, tab2 = st.tabs(["Калькулятор", "Сохранённые результаты"])

with tab1:
    st.title("⛏️ Калькулятор майнинга Bitcoin")
    col_params, col_results = st.columns([1, 2])
    
    with col_params:
        st.header("Параметры оборудования")
        asic_count = st.number_input("Количество ASIC", min_value=1, value=1)
        asic_hashrate = st.number_input("Хешрейт 1 ASIC (TH/s)", min_value=1, value=120)
        asic_power = st.number_input("Потребление 1 ASIC (Вт)", min_value=100, value=3600)
        asic_price = st.number_input("Стоимость 1 ASIC ($)", min_value=1, value=500)
        electricity = st.number_input("Электричество (руб/кВт·ч)", min_value=1.0, value=6.4)
        
        # Используем session_state для хранения состояния чекбокса
        show_in_usd = st.checkbox("Показать расчеты в $", value=st.session_state.show_in_usd)
        st.session_state.show_in_usd = show_in_usd
        
        if st.button("🔄 Обновить курсы"):
            st.session_state.usd_rub_rate = get_usd_rub_rate()
            st.session_state.btc_price_usd = get_btc_price()
            st.success("Курсы обновлены!")
        
        usd_rub = get_usd_rub_rate()
        btc_usd = get_btc_price()
        st.metric("Курс USD/RUB", f"{format_number(usd_rub, 2)} ₽")
        st.metric("Цена BTC", f"{format_number(btc_usd, 2)} $")

        st.header("Сценарии доходности")
        if not st.session_state.scenarios:
            add_scenario()

        for i, scenario in enumerate(st.session_state.scenarios):
            with st.container(border=True):
                cols = st.columns(2)
                with cols[0]:
                    start = st.number_input("С", min_value=1, value=scenario['start'], key=f"start_{i}", step=1)
                with cols[1]:
                    end = st.number_input("По", min_value=start, value=scenario['end'], key=f"end_{i}", step=1)
                
                reinvest = st.slider("Реинвестиции %", 0, 100, scenario['reinvest'], key=f"reinvest_{i}")
                wallet = st.slider("Кошелек %", 0, 100, scenario['wallet'], key=f"wallet_{i}")
                
                if st.button("❌ Удалить", key=f"remove_{i}"):
                    remove_scenario(i)
                    st.rerun()
                
                st.session_state.scenarios[i] = {
                    "start": start,
                    "end": end,
                    "reinvest": reinvest,
                    "wallet": wallet
                }

        if st.button("➕ Добавить период"):
            add_scenario()
            st.rerun()

    if st.button("🔄 Рассчитать", type="primary", use_container_width=True):
        with col_results:
            with st.spinner("Выполняю расчет..."):
                usd_rub = get_usd_rub_rate()
                btc_usd = get_btc_price()
                electricity_usd = electricity / usd_rub
                
                mining_data = get_mining_data_with_retry(asic_hashrate, asic_power, electricity_usd)
                
                # Основные расчеты
                daily_revenue_per_asic_usd = mining_data["daily_revenue"]
                daily_cost_per_asic_usd = (asic_power / 1000) * 24 * electricity_usd
                daily_profit_per_asic_usd = daily_revenue_per_asic_usd - daily_cost_per_asic_usd
                
                if st.session_state.show_in_usd:
                    daily_revenue_per_asic = daily_revenue_per_asic_usd
                    daily_cost_per_asic = daily_cost_per_asic_usd
                    daily_profit_per_asic = daily_profit_per_asic_usd
                    asic_price_curr = asic_price
                else:
                    daily_revenue_per_asic = daily_revenue_per_asic_usd * usd_rub
                    daily_cost_per_asic = daily_cost_per_asic_usd * usd_rub
                    daily_profit_per_asic = daily_profit_per_asic_usd * usd_rub
                    asic_price_curr = asic_price * usd_rub
                
                current_asics = asic_count
                savings = 0
                wallet_btc = 0
                results = []
                total_months = max(s["end"] for s in st.session_state.scenarios) if st.session_state.scenarios else 12
                
                total_investment = asic_count * asic_price_curr
                cumulative_profit = 0
                break_even_month = None
                
                for month in range(1, total_months + 1):
                    active_scenario = next(
                        (s for s in st.session_state.scenarios if s["start"] <= month <= s["end"]),
                        {"reinvest": 50, "wallet": 10}
                    )
                    
                    revenue = daily_revenue_per_asic * 30 * current_asics
                    cost = daily_cost_per_asic * 30 * current_asics
                    profit = daily_profit_per_asic * 30 * current_asics
                    
                    to_reinvest = profit * (active_scenario["reinvest"] / 100)
                    salary = profit - to_reinvest
                    to_wallet = to_reinvest * (active_scenario["wallet"] / 100)
                    to_asics = to_reinvest - to_wallet
                    
                    savings += to_asics
                    btc_amount = to_wallet / (btc_usd * (usd_rub if not st.session_state.show_in_usd else 1))
                    wallet_btc += btc_amount
                    
                    new_asics = int(savings // asic_price_curr)
                    if new_asics > 0:
                        current_asics += new_asics
                        savings -= new_asics * asic_price_curr
                    
                    cumulative_profit += profit
                    if cumulative_profit >= total_investment and break_even_month is None:
                        break_even_month = month
                    
                    wallet_value = wallet_btc * btc_usd * (usd_rub if not st.session_state.show_in_usd else 1)
                    wallet_str = f"{wallet_btc:.8f} BTC ({format_number(wallet_value, 2, 'usd' if st.session_state.show_in_usd else 'rub')})"
                    
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доходы": int(revenue),
                        "Расходы": int(cost),
                        "Прибыль": int(profit),
                        "Зарплата": int(salary),
                        "Реинвест": int(to_reinvest),
                        "В кошелек": int(to_wallet),
                        "Накопления": int(savings),
                        "Кошелек": wallet_str,
                        "Сценарий": f"{active_scenario['start']}-{active_scenario['end']}"
                    })
                
                df = pd.DataFrame(results)
                st.session_state.current_results = df

    if st.session_state.current_results is not None:
        with col_results:
            st.dataframe(
                st.session_state.current_results.style.format({
                    "Доходы": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "Расходы": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "Прибыль": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "Зарплата": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "Реинвест": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "В кошелек": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub"),
                    "Накопления": lambda x: format_number(x, 0, "usd" if st.session_state.show_in_usd else "rub")
                }),
                hide_index=True,
                use_container_width=True,
                height=700,
                column_config={
                    "Месяц": st.column_config.NumberColumn(width="small"),
                    "ASIC": st.column_config.NumberColumn(width="small"),
                    "Сценарий": st.column_config.TextColumn(width="medium")
                }
            )
            
            with st.form("save_form"):
                result_name = st.text_input("Название сохранения", 
                                          value=f"Результат {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                if st.form_submit_button("💾 Сохранить результаты"):
                    if result_name.strip():
                        st.session_state.saved_results[result_name] = {
                            "timestamp": datetime.now().isoformat(),
                            "data": st.session_state.current_results.to_dict('records'),
                            "params": {
                                "asic_count": asic_count,
                                "asic_hashrate": asic_hashrate,
                                "asic_power": asic_power,
                                "asic_price": asic_price,
                                "electricity": electricity,
                                "show_in_usd": st.session_state.show_in_usd,
                                "usd_rub_rate": usd_rub,
                                "btc_price_usd": btc_usd,
                                "scenarios": st.session_state.scenarios.copy()
                            }
                        }
                        st.success(f"Сохранено: {result_name}")
                        st.rerun()

with tab2:
    st.title("📁 Сохранённые результаты")
    
    if not st.session_state.saved_results:
        st.info("Нет сохранённых результатов")
    else:
        selected = st.multiselect(
            "Выберите 2-3 результата для анализа:",
            options=list(st.session_state.saved_results.keys()),
            max_selections=3
        )
        
        if st.button("🧠 Получить экспертный анализ DeepSeek", 
                    disabled=len(selected) < 2,
                    help="Персональные выводы от ИИ на основе ваших данных"):
            with st.spinner("DeepSeek анализирует..."):
                analysis = generate_ai_analysis(selected)
                st.markdown(analysis)
                st.session_state.last_ai_analysis = analysis
        
        if 'last_ai_analysis' in st.session_state:
            with st.expander("Последний анализ", expanded=True):
                st.markdown(st.session_state.last_ai_analysis)
        
        for name, data in st.session_state.saved_results.items():
            with st.expander(f"📌 {name} ({data['timestamp']})"):
                st.write("Параметры расчета:")
                st.json(data["params"])
                
                df = pd.DataFrame(data["data"])
                show_in_usd_saved = data["params"].get("show_in_usd", False)
                
                st.dataframe(
                    df.style.format({
                        "Доходы": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "Расходы": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "Прибыль": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "Зарплата": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "Реинвест": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "В кошелек": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"),
                        "Накопления": lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub")
                    }),
                    hide_index=True,
                    use_container_width=True,
                    height=700
                )
                
                if st.button(f"❌ Удалить {name}"):
                    del st.session_state.saved_results[name]
                    st.rerun()