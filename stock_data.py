import re
import logging
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

COMPANY_ALIASES = {
    "apple": "AAPL", "google": "GOOGL", "alphabet": "GOOGL", "tesla": "TSLA",
    "microsoft": "MSFT", "amazon": "AMZN", "meta": "META", "facebook": "META",
    "netflix": "NFLX", "nvidia": "NVDA", "intel": "INTC", "amd": "AMD",
    "ibm": "IBM", "oracle": "ORCL", "salesforce": "CRM", "adobe": "ADBE",
    "paypal": "PYPL", "uber": "UBER", "airbnb": "ABNB", "disney": "DIS",
    "coca cola": "KO", "coca-cola": "KO", "pepsi": "PEP", "walmart": "WMT",
    "jpmorgan": "JPM", "jp morgan": "JPM", "visa": "V", "mastercard": "MA",
    "boeing": "BA", "nike": "NKE", "starbucks": "SBUX", "reliance": "RELIANCE.NS",
    "infosys": "INFY", "tcs": "TCS.NS",
}

EXPLICIT_TICKER_PATTERN = re.compile(r'\b[A-Z]{2,5}\b')

STOPWORDS = {
    "I", "A", "THE", "AND", "OR", "FOR", "TO", "OF", "IN", "ON", "MY", "ME",
    "IS", "IT", "AT", "BE", "AS", "BY", "AN", "SO", "IF", "US", "GIVE", "PRICE",
    "STOCK", "STOCKS", "BASED", "THESE", "THIS", "THAT", "WANT", "NEED", "REAL",
    "TIME", "VALUE", "TOTAL", "EACH", "ALL", "GET", "SHOW", "MAKE", "WITH",
    "FROM", "HAVE", "HAS", "WHAT", "WHO", "HOW", "CAN", "WILL", "NOW", "DATA",
    "COST", "COSTS", "AMOUNT", "CURRENT", "ARE", "YOU", "YOUR",
}


def find_candidate_tickers(text):
    candidates = {}
    lowered = text.lower()
    for name, ticker in COMPANY_ALIASES.items():
        if name in lowered:
            candidates[ticker] = name.title()
    for m in EXPLICIT_TICKER_PATTERN.findall(text):
        if m not in STOPWORDS and m not in candidates:
            candidates[m] = m
    return candidates


def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        try:
            fast = stock.fast_info
            for key in ("last_price", "lastPrice", "regularMarketPrice"):
                try:
                    price = fast[key]
                    if price:
                        currency = "USD"
                        try:
                            currency = fast["currency"]
                        except Exception:
                            pass
                        return {"price": round(float(price), 2), "currency": currency}
                except Exception:
                    continue
        except Exception:
            pass

        hist = stock.history(period="1d")
        if not hist.empty:
            price = hist["Close"].iloc[-1]
            if price:
                return {"price": round(float(price), 2), "currency": "USD"}
    except Exception:
        pass
    return None


def get_stock_context(text):
    candidates = find_candidate_tickers(text)
    if not candidates:
        return ""

    items = list(candidates.items())[:6]

    # fetch all prices concurrently instead of one-by-one — these are independent
    # network calls, so running them in parallel cuts total wait time significantly
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(get_stock_price, ticker): (ticker, label) for ticker, label in items}
        results = []
        for future in futures:
            ticker, label = futures[future]
            data = future.result()
            if data:
                results.append((ticker, label, data))

    if not results:
        return ""

    lines = [f"- {label} ({ticker}): {data['price']} {data['currency']}" for ticker, label, data in results]
    return "REAL, CURRENT STOCK PRICES — use these exact values, do not invent or estimate different numbers:\n" + "\n".join(lines)