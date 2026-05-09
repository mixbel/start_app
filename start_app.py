import streamlit as st
import pandas as pd
import requests
import time
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
    "network_data": {"value": None, "timestamp": None, "expires": 3600}  # Кэш для сложности и награды
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

def get_network_difficulty_and_reward():
    """Получаем текущую сложность сети и награду за блок с blockchain.info"""
    cached = get_cached_data("network_data")
    if cached:
        return cached
    
    try:
        # Получаем сложность сети
        difficulty_response = requests.get("https://blockchain.info/q/getdifficulty", timeout=10)
        difficulty = float(difficulty_response.text)
        
        # Получаем текущую награду за блок (API сам учитывает халвинги)
        reward_response = requests.get("https://blockchain.info/q/blockreward", timeout=10)
        block_reward = float(reward_response.text)
        
        result = {
            "difficulty": difficulty,
            "block_reward": block_reward
        }
        
        set_cached_data("network_data", result)
        return result
        
    except Exception as e:
        # Если API не работает, возвращаем примерные значения
        # Текущая сложность ~100T, награда 6.25 BTC
        return {
            "difficulty": 100_000_000_000_000,
            "block_reward": 6.25
        }

def get_mining_revenue_per_th_per_day():
    """
    Рассчитываем доходность 1 TH/s в сутки в USD
    Использует реальные данные сложности и награды из API
    """
    try:
        # Получаем актуальные данные
        network_data = get_network_difficulty_and_reward()
        difficulty = network_data["difficulty"]
        block_reward = network_data["block_reward"]
        btc_usd = get_btc_price()
        
        # Константы
        seconds_per_day = 86400
        seconds_per_block = 600  # 10 минут между блоками в среднем
        
        # Количество хэшей для нахождения одного блока при текущей сложности
        # Формула: difficulty * 2^32 (где 2^32 = 4294967296)
        hashes_per_block = difficulty * 4294967296
        
        # Хэшрейт 1 TH/s в хэшах в день
        hash_rate_th_per_second = 1e12  # 1 TH/s = 1,000,000,000,000 хэш/с
        hash_rate_th_per_day = hash_rate_th_per_second * seconds_per_day
        
        # Ожидаемое количество блоков, которое найдет 1 TH/s в день
        blocks_found_per_day = hash_rate_th_per_day / hashes_per_block
        
        # Доход в BTC в день для 1 TH/s
        btc_per_day = blocks_found_per_day * block_reward
        
        # Конвертируем в USD
        return btc_per_day * btc_usd
        
    except Exception as e:
        # Если расчет не удался, возвращаем реалистичное значение
        # При сложности ~100T: около 0.00000035 BTC/TH/день
        btc_usd = get_btc_price()
        estimated_btc_per_th = 0.00000035
        return estimated_btc_per_th * btc_usd

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
        
        st.subheader("Халвинг Bitcoin")
        halving_date = st.date_input(
            "Дата следующего халвинга",
            value=datetime(2028, 4, 1),
            min_value=datetime.today(),
            help="После этой даты награда за блок уменьшится в 2 раза",
            key="halving_date"
        )
        
        today = datetime.today().date()
        if halving_date > today:
            months_to_halving = (halving_date.year - today.year) * 12 + (halving_date.month - today.month)
            if months_to_halving <= 1:
                st.info(f"⚠️ Халвинг наступит через {months_to_halving} месяц(ев)")
            else:
                st.info(f"📅 Халвинг наступит через {months_to_halving} месяцев")
        elif halving_date == today:
            st.warning("⚠️ Халвинг наступает сегодня!")
        else:
            st.warning("⚠️ Выбранная дата уже прошла, халвинг уже должен был произойти")
        
        show_in_usd = st.checkbox("Показать расчеты в $", value=False, key="show_in_usd")
        
        if st.button("🔄 Обновить курсы"):
            for key in API_CACHE:
                API_CACHE[key]["value"] = None
                API_CACHE[key]["timestamp"] = None
            st.success("Курсы и данные сети обновлены!")
        
        usd_rub = get_usd_rub_rate()
        btc_usd = get_btc_price()
        network_data = get_network_difficulty_and_reward()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Курс USD/RUB", f"{format_number(usd_rub, 2)} ₽")
        with col2:
            st.metric("Цена BTC", f"{format_number(btc_usd, 2)} $")
        with col3:
            st.metric("Награда за блок", f"{network_data['block_reward']} BTC")
        
        # Показываем примерную доходность
        revenue_per_th = get_mining_revenue_per_th_per_day()
        st.caption(f"💰 Текущая доходность: ~{format_number(revenue_per_th * asic_hashrate, 2, 'usd')}/день")

        # Блок сценариев
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

    # Кнопка расчета
    if st.button("🔄 Рассчитать", type="primary", use_container_width=True, key="calculate_btn"):
        with st.spinner("Выполняю расчет..."):
            usd_rub = get_usd_rub_rate()
            btc_usd = get_btc_price()
            
            # Получаем базовую доходность 1 TH/s в день
            revenue_per_th_per_day_usd = get_mining_revenue_per_th_per_day()
            
            # Общий хешрейт
            total_hashrate_th = asic_hashrate * asic_count
            
            # Базовый дневной доход в USD
            base_daily_revenue_usd = revenue_per_th_per_day_usd * total_hashrate_th
            
            # Дневные расходы на электричество
            daily_power_cost_rub = (asic_power / 1000) * 24 * electricity * asic_count
            daily_power_cost_usd = daily_power_cost_rub / usd_rub
            
            # Инициализация
            current_asics = asic_count
            current_hashrate_th = asic_hashrate * current_asics
            savings = 0
            wallet_btc = 0
            results = []
            
            total_investment = asic_count * asic_price * usd_rub
            total_investment_usd = asic_count * asic_price
            cumulative_profit = 0
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
                
                # ДОХОД
                monthly_revenue = base_daily_revenue_usd * 30
                
                # Рост сложности
                difficulty_multiplier = (1 + difficulty_growth) ** (month - 1)
                monthly_revenue = monthly_revenue / difficulty_multiplier if difficulty_multiplier > 0 else monthly_revenue
                
                # Халвинг
                if current_date >= halving_datetime:
                    monthly_revenue = monthly_revenue * 0.5
                
                # Пересчет в рубли
                monthly_revenue_rub = monthly_revenue * usd_rub
                
                # КОМИССИЯ ПУЛА
                pool_fee_amount = monthly_revenue * pool_fee
                pool_fee_amount_rub = pool_fee_amount * usd_rub
                
                # ЭЛЕКТРИКА
                electricity_cost = daily_power_cost_usd * 30
                electricity_cost_rub = electricity_cost * usd_rub
                
                # ОБЩИЕ РАСХОДЫ
                total_costs = pool_fee_amount + electricity_cost
                total_costs_rub = total_costs * usd_rub
                
                # ПРИБЫЛЬ ДО НАЛОГА
                profit_before_tax = monthly_revenue - total_costs
                profit_before_tax_rub = profit_before_tax * usd_rub
                
                # НАЛОГ
                if profit_before_tax > 0:
                    tax = profit_before_tax * tax_rate
                    tax_rub = tax * usd_rub
                    net_profit = profit_before_tax - tax
                    net_profit_rub = net_profit * usd_rub
                else:
                    tax = 0
                    tax_rub = 0
                    net_profit = profit_before_tax
                    net_profit_rub = profit_before_tax_rub
                
                # Распределение чистой прибыли
                to_reinvest = net_profit * (reinvest_percent / 100)
                salary = net_profit - to_reinvest
                to_wallet = to_reinvest * (wallet_percent / 100)
                to_asics = to_reinvest - to_wallet
                
                savings += to_asics
                btc_amount = to_wallet / btc_usd
                wallet_btc += btc_amount
                
                # Покупка новых ASIC
                if savings >= asic_price:
                    new_asics = int(savings // asic_price)
                    current_asics += new_asics
                    current_hashrate_th = asic_hashrate * current_asics
                    savings -= new_asics * asic_price
                    base_daily_revenue_usd = revenue_per_th_per_day_usd * current_hashrate_th
                    daily_power_cost_usd = (asic_power / 1000) * 24 * electricity * current_asics / usd_rub
                    daily_power_cost_rub = (asic_power / 1000) * 24 * electricity * current_asics
                
                # Окупаемость
                cumulative_profit += profit_before_tax
                investment_for_break_even = total_investment_usd if show_in_usd else total_investment
                if cumulative_profit >= investment_for_break_even and break_even_month is None:
                    break_even_month = month
                
                cumulative_net_profit += net_profit
                if cumulative_net_profit >= investment_for_break_even and clean_break_even_month is None:
                    clean_break_even_month = month
                
                # Формирование результата
                if show_in_usd:
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доход": int(monthly_revenue),
                        "Комиссия пула": int(pool_fee_amount),
                        "Электрика": int(electricity_cost),
                        "Расходы": int(total_costs),
                        "Прибыль": int(profit_before_tax),
                        "Налог": int(tax),
                        "Чистая прибыль": int(net_profit),
                        "Зарплата": int(salary),
                        "Реинвест": int(to_reinvest),
                        "В кошелек": int(to_wallet),
                        "Накопления": int(savings),
                        "Кошелек BTC": f"{wallet_btc:.8f} BTC",
                        "Кошелек USD": format_number(wallet_btc * btc_usd, 2, 'usd')
                    })
                else:
                    results.append({
                        "Месяц": month,
                        "ASIC": current_asics,
                        "Доход": int(monthly_revenue_rub),
                        "Комиссия пула": int(pool_fee_amount_rub),
                        "Электрика": int(electricity_cost_rub),
                        "Расходы": int(total_costs_rub),
                        "Прибыль": int(profit_before_tax_rub),
                        "Налог": int(tax_rub),
                        "Чистая прибыль": int(net_profit_rub),
                        "Зарплата": int(salary * usd_rub),
                        "Реинвест": int(to_reinvest * usd_rub),
                        "В кошелек": int(to_wallet * usd_rub),
                        "Накопления": int(savings * usd_rub),
                        "Кошелек BTC": f"{wallet_btc:.8f} BTC",
                        "Кошелек RUB": format_number(wallet_btc * btc_usd * usd_rub, 0, 'rub')
                    })
            
            df = pd.DataFrame(results)
            st.session_state.current_results = df
            st.rerun()

    # Отображение результатов
    with col_results:
        if st.session_state.current_results is not None:
            df = st.session_state.current_results.copy()
            usd_rub = get_usd_rub_rate()
            btc_usd = get_btc_price()
            
            initial_investment = asic_count * asic_price * (usd_rub if not show_in_usd else 1)
            
            # Окупаемость
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
            
            # Сводные данные
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
                    format_number(df['Чистая прибыль'].sum(), 0, "usd" if show_in_usd else "rub"),
                    f"{df.iloc[-1]['ASIC']} шт.",
                    df.iloc[-1]['Кошелек BTC']
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df.style.hide(axis="index"), hide_index=True, use_container_width=True)
            
            display_columns = ["Месяц", "ASIC", "Доход", "Комиссия пула", "Электрика", "Расходы", 
                              "Прибыль", "Налог", "Чистая прибыль", "Зарплата", "Реинвест", 
                              "В кошелек", "Накопления", "Кошелек BTC"]
            if show_in_usd:
                display_columns.append("Кошелек USD")
            else:
                display_columns.append("Кошелек RUB")
            
            formatted_df = df[display_columns].copy()
            for col in ["Доход", "Комиссия пула", "Электрика", "Расходы", "Прибыль", 
                       "Налог", "Чистая прибыль", "Зарплата", "Реинвест", "В кошелек", "Накопления"]:
                if col in formatted_df.columns:
                    formatted_df[col] = formatted_df[col].apply(lambda x: format_number(x, 0, "usd" if show_in_usd else "rub"))
            
            st.dataframe(formatted_df, hide_index=True, use_container_width=True, height=700)
            
            # Форма сохранения
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
                                    "halving_date": halving_date.isoformat(),
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
    if not st.session_state.get('saved_results', {}):
        st.info("Нет сохраненных результатов")
    else:
        saved_results_copy = st.session_state.saved_results.copy()
        for name, data in saved_results_copy.items():
            with st.expander(f"📌 {name} ({data['timestamp']})"):
                st.write("Параметры расчета:")
                st.json(data["params"])
                if "summary" in data:
                    st.write("Сводные данные:")
                    summary_df = pd.DataFrame(data["summary"])
                    st.dataframe(summary_df.style.hide(axis="index"), hide_index=True, use_container_width=True)
                df = pd.DataFrame(data["data"])
                show_in_usd_saved = data["params"].get("show_in_usd", False)
                display_columns = ["Месяц", "ASIC", "Доход", "Комиссия пула", "Электрика", "Расходы", 
                                  "Прибыль", "Налог", "Чистая прибыль", "Зарплата", "Реинвест", 
                                  "В кошелек", "Накопления", "Кошелек BTC"]
                if show_in_usd_saved and "Кошелек USD" in df.columns:
                    display_columns.append("Кошелек USD")
                elif not show_in_usd_saved and "Кошелек RUB" in df.columns:
                    display_columns.append("Кошелек RUB")
                formatted_df = df[display_columns].copy()
                for col in ["Доход", "Комиссия пула", "Электрика", "Расходы", "Прибыль", 
                           "Налог", "Чистая прибыль", "Зарплата", "Реинвест", "В кошелек", "Накопления"]:
                    if col in formatted_df.columns:
                        formatted_df[col] = formatted_df[col].apply(lambda x: format_number(x, 0, "usd" if show_in_usd_saved else "rub"))
                st.dataframe(formatted_df, hide_index=True, use_container_width=True)
                if st.button(f"❌ Удалить {name}", key=f"delete_{name}"):
                    del st.session_state.saved_results[name]
                    st.rerun()
