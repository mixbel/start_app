import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

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
    """Получаем данные из кэша если они актуальны"""
    if API_CACHE[key]["value"] and API_CACHE[key]["timestamp"]:
        elapsed = time.time() - API_CACHE[key]["timestamp"]
        if elapsed < API_CACHE[key]["expires"]:
            return API_CACHE[key]["value"]
    return None

def set_cached_data(key, value):
    """Обновляем данные в кэше"""
    API_CACHE[key]["value"] = value
    API_CACHE[key]["timestamp"] = time.time()

def fetch_with_fallback(urls, parse_funcs):
    """Пытаемся получить данные из нескольких источников"""
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
    """Получаем курс BTC с нескольких бирж"""
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
    """Получаем курс USD/RUB с нескольких источников"""
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
    """Получаем данные о майнинге с повторными попытками"""
    cached = get_cached_data("mining_data")
    if cached:
        return cached
    
    for attempt in range(retries):
        try:
            params = {
                "hr": hashrate_th,
                "p": power_w,
                "cost": electricity_cost_usd,
                "fee": 1.0,
                "commit": "Calculate"
            }
            response = requests.get("https://whattomine.com/coins/1.json", 
                                 params=params, timeout=10)
            data = response.json()
            result = {
                "daily_profit": float(data["profit"].replace('$', '').replace(',', '')),
                "daily_revenue": float(data["revenue"].replace('$', '').replace(',', ''))
            }
            set_cached_data("mining_data", result)
            return result
        except:
            if attempt == retries - 1:
                return {
                    "daily_profit": 12.50,
                    "daily_revenue": 18.00
                }
            time.sleep(1 * (attempt + 1))

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
    # Перенумеруем оставшиеся сценарии
    for i in range(len(st.session_state.scenarios)):
        if i == 0:
            st.session_state.scenarios[i]["start"] = 1
        else:
            st.session_state.scenarios[i]["start"] = st.session_state.scenarios[i-1]["end"] + 1
        st.session_state.scenarios[i]["end"] = st.session_state.scenarios[i]["start"] + 11

# --- Основные функции калькулятора ---
def format_number(value, decimals=0, currency="rub"):
    """Форматирует число с пробелами между тысячами"""
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
    page_title="Калькулятор майнинга PRO",
    page_icon="⛏️",
    layout="wide"
)

# Создаем вкладки
tab1, tab2 = st.tabs(["Калькулятор", "Сохраненные результаты"])

with tab1:
    st.title("⛏️ Калькулятор майнинга Bitcoin")
    
    # Изменяем разметку - теперь параметры слева, таблица справа
    col_params, col_results = st.columns([1, 2], gap="large")
    
    with col_params:
        st.header("Параметры оборудования")
        asic_count = st.number_input("Количество ASIC", min_value=1, value=1)
        asic_hashrate = st.number_input("Хешрейт 1 ASIC (TH/s)", min_value=1, value=120)
        asic_power = st.number_input("Потребление 1 ASIC (Вт)", min_value=100, value=3600)
        asic_price = st.number_input("Стоимость 1 ASIC ($)", min_value=1, value=500)
        electricity = st.number_input("Электричество (руб/кВт·ч)", min_value=1.0, value=6.4)
        
        show_in_usd = st.checkbox("Показать расчеты в $", value=False)
        
        if st.button("🔄 Обновить курсы"):
            st.session_state.usd_rub_rate = get_usd_rub_rate()
            st.session_state.btc_price_usd = get_btc_price()
            st.success("Курсы обновлены!")
        
        usd_rub = get_usd_rub_rate()
        btc_usd = get_btc_price()
        st.metric("Курс USD/RUB", f"{format_number(usd_rub, 2)} ₽")
        st.metric("Цена BTC", f"{format_number(btc_usd, 2)} $")

        # Блок сценариев
        st.header("Сценарии доходности")
        if not st.session_state.scenarios:
            add_scenario()

        for i, scenario in enumerate(st.session_state.scenarios):
            with st.container(border=True):
                cols = st.columns(2)
                with cols[0]:
                    start = st.number_input("С", min_value=1, value=scenario['start'], 
                                          key=f"start_{i}", step=1)
                with cols[1]:
                    end = st.number_input("По", min_value=start, value=scenario['end'], 
                                        key=f"end_{i}", step=1)
                
                reinvest = st.slider("Реинвестиции %", 0, 100, scenario['reinvest'], 
                                   key=f"reinvest_{i}")
                wallet = st.slider("Кошелек %", 0, 100, scenario['wallet'], 
                                 key=f"wallet_{i}")
                
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

   # Кнопка расчета теперь в основном потоке, а не в колонке
    if st.button("🔄 Рассчитать", type="primary", use_container_width=True):
        with st.spinner("Выполняю расчет..."):
            # Получаем данные
            usd_rub = get_usd_rub_rate()
            btc_usd = get_btc_price()
            electricity_usd = electricity / usd_rub
            
            # Получаем данные для 1 ASIC
            mining_data_per_asic = get_mining_data_with_retry(
                asic_hashrate,
                asic_power,
                electricity_usd
            )
            
            # Масштабируем на количество ASIC
            daily_profit_per_asic_usd = mining_data_per_asic["daily_profit"]
            daily_cost_per_asic_usd = (asic_power / 1000) * 24 * electricity_usd
            
            daily_profit_per_asic_rub = daily_profit_per_asic_usd * usd_rub
            daily_cost_per_asic_rub = (asic_power / 1000) * 24 * electricity
            
            # Инициализация
            current_asics = asic_count
            savings = 0
            wallet_btc = 0
            results = []
            
            # Для расчета окупаемости
            total_investment = asic_count * asic_price * usd_rub
            total_investment_usd = asic_count * asic_price
            cumulative_profit = 0
            break_even_month = None
            
            # Определяем общее количество месяцев из сценариев
            total_months = max(s["end"] for s in st.session_state.scenarios) if st.session_state.scenarios else 12
            
            for month in range(1, total_months + 1):
                # Находим активный сценарий для текущего месяца
                active_scenario = None
                for scenario in st.session_state.scenarios:
                    if scenario["start"] <= month <= scenario["end"]:
                        active_scenario = scenario
                        break
                
                if not active_scenario:
                    continue
                
                # Используем параметры из активного сценария
                reinvest_percent = active_scenario["reinvest"]
                wallet_percent = active_scenario["wallet"]
                
                # Расчет прибыли и расходов
                profit = daily_profit_per_asic_rub * 30 * current_asics
                cost = daily_cost_per_asic_rub * 30 * current_asics
                
                # Распределение средств
                to_reinvest = profit * (reinvest_percent / 100)
                salary = profit - to_reinvest
                
                to_wallet = to_reinvest * (wallet_percent / 100)
                to_asics = to_reinvest - to_wallet
                
                savings += to_asics
                btc_amount = to_wallet / usd_rub / btc_usd
                wallet_btc += btc_amount
                
                # Покупка ASIC
                new_asics = int(savings // (asic_price * usd_rub))
                if new_asics > 0:
                    current_asics += new_asics
                    savings -= new_asics * asic_price * usd_rub
                
                # Расчет окупаемости
                cumulative_profit += profit
                if cumulative_profit >= total_investment and break_even_month is None:
                    break_even_month = month
                
                # Конвертация в доллары если выбрано
                if show_in_usd:
                    profit_usd = profit / usd_rub
                    cost_usd = cost / usd_rub
                    salary_usd = salary / usd_rub
                    to_reinvest_usd = to_reinvest / usd_rub
                    to_wallet_usd = to_wallet / usd_rub
                    savings_usd = savings / usd_rub
                    
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доходы": int(profit_usd + cost_usd),
                        "Расходы": int(cost_usd),
                        "Прибыль": int(profit_usd),
                        "Зарплата": int(salary_usd),
                        "Реинвест": int(to_reinvest_usd),
                        "В кошелек": int(to_wallet_usd),
                        "Накопления": int(savings_usd),
                        "Кошелек": f"{wallet_btc:.8f} BTC (${format_number(wallet_btc * btc_usd, 2, 'usd')})"
                    })
                else:
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доходы": int(profit + cost),
                        "Расходы": int(cost),
                        "Прибыль": int(profit),
                        "Зарплата": int(salary),
                        "Реинвест": int(to_reinvest),
                        "В кошелек": int(to_wallet),
                        "Накопления": int(savings),
                        "Кошелек": f"{wallet_btc:.8f} BTC ({format_number(wallet_btc * btc_usd * usd_rub, 0, 'rub')})"
                    })
            
            # Создаем DataFrame с результатами
            df = pd.DataFrame(results)
            st.session_state.current_results = df
            st.rerun()

    # Отображение результатов в правой колонке
    with col_results:
        if st.session_state.current_results is not None:
            # Вычисляем сводные данные
            df = st.session_state.current_results.copy()
            
            # Первоначальные инвестиции
            initial_investment = asic_count * asic_price * (usd_rub if not show_in_usd else 1)
            
            # Окупаемость чистая (по зарплате + кошелек)
            cumulative_salary_wallet = 0
            clean_break_even_month = None
            for _, row in df.iterrows():
                salary = row['Зарплата']
                wallet_value_str = row['Кошелек'].split('(')[1].split(')')[0].replace('$', '').replace('₽', '').replace(' ', '').replace(',', '.').strip()
                try:
                    wallet_value = float(wallet_value_str)
                except ValueError:
                    wallet_value = 0
                cumulative_salary_wallet += salary + wallet_value
                if cumulative_salary_wallet >= initial_investment and clean_break_even_month is None:
                    clean_break_even_month = row['Месяц']
            
            # Окупаемость грязная (по прибыли)
            cumulative_profit = df['Прибыль'].cumsum()
            dirty_break_even_month = None
            for _, row in df.iterrows():
                if cumulative_profit[row['Месяц']-1] >= initial_investment:
                    dirty_break_even_month = row['Месяц']
                    break
            
            # Общая прибыль и затраты на электричество
            total_profit = df['Прибыль'].sum()
            total_electricity = df['Расходы'].sum()
            
            # Создаем таблицу со сводными данными
            summary_data = {
                "Показатель": [
                    "Первоначальные инвестиции", 
                    "Окупаемость чистая (мес)", 
                    "Окупаемость грязная (мес)",
                    "Общая прибыль",
                    "Сумма за электрику"
                ],
                "Значение": [
                    format_number(initial_investment, 0, "usd" if show_in_usd else "rub"),
                    clean_break_even_month if clean_break_even_month else "Не окупилось",
                    dirty_break_even_month if dirty_break_even_month else "Не окупилось",
                    format_number(total_profit, 0, "usd" if show_in_usd else "rub"),
                    format_number(total_electricity, 0, "usd" if show_in_usd else "rub")
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.session_state.current_summary = summary_df.to_dict('records')
            
            # Отображаем сводные данные и основную таблицу
            st.dataframe(
                summary_df.style.hide(axis="index"),
                hide_index=True,
                use_container_width=True
            )
            
            st.dataframe(
                df.style.format({
                    "Доходы": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "Расходы": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "Прибыль": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "Зарплата": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "Реинвест": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "В кошелек": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"),
                    "Накопления": lambda x: format_number(x, 0, "usd" if show_in_usd else "rub")
                }),
                hide_index=True,
                use_container_width=True,
                height=700,
                column_config={
                    "Месяц": st.column_config.NumberColumn(width="small"),
                    "ASIC": st.column_config.NumberColumn(width="small")
                }
            )

            # Форма для сохранения
            with st.form("save_form"):
                result_name = st.text_input("Название сохранения", 
                                          value=f"Результат {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                if st.form_submit_button("💾 Сохранить результаты"):
                    if result_name.strip():
                        if result_name in st.session_state.saved_results:
                            st.error("Результат с таким названием уже существует!")
                        else:
                            st.session_state.saved_results[result_name] = {
                                "timestamp": datetime.now().isoformat(),
                                "data": st.session_state.current_results.to_dict('records'),
                                "summary": st.session_state.current_summary,
                                "params": {
                                    "asic_count": asic_count,
                                    "asic_hashrate": asic_hashrate,
                                    "asic_power": asic_power,
                                    "asic_price": asic_price,
                                    "electricity": electricity,
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
    st.title("📁 Сохраненные результаты")
    
    # Проверяем наличие сохраненных результатов в session_state
    if not st.session_state.get('saved_results', {}):
        st.info("Нет сохраненных результатов")
    else:
        # Создаем копию словаря, чтобы избежать изменений во время итерации
        saved_results_copy = st.session_state.saved_results.copy()
        
        for name, data in saved_results_copy.items():
            with st.expander(f"📌 {name} ({data['timestamp']})"):
                st.write("Параметры расчета:")
                st.json(data["params"])
                
                # Отображаем сводные данные
                if "summary" in data:
                    st.write("Сводные данные:")
                    summary_df = pd.DataFrame(data["summary"])
                    st.dataframe(
                        summary_df.style.hide(axis="index"),
                        hide_index=True,
                        use_container_width=True
                    )
                
                # Восстанавливаем DataFrame
                df = pd.DataFrame(data["data"])
                
                # Определяем валюту для форматирования
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
                    use_container_width=True
                )
                
                if st.button(f"❌ Удалить {name}"):
                    del st.session_state.saved_results[name]
                    st.rerun()