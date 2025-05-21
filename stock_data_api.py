import requests
from datetime import datetime, timedelta
import json
import logging

# Get API Key from config
import config

FINNHUB_API_KEY = config.FINNHUB_API_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_data(symbol):
    """Fetch stock data from Finnhub API."""
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        data = response.json()
        
        if data and data.get('c') is not None: # 'c' is the current price
            # Finnhub Quote API fields:
            # c: Current price
            # h: High price of the day
            # l: Low price of the day
            # o: Open price of the day
            # pc: Previous close price
            # t: Unix timestamp

            # Calculate change and percentage change
            current_price = data['c']
            previous_close = data['pc']

            if previous_close is None or previous_close == 0:
                change = 0.0
                percent_change = 0.0
            else:
                change = current_price - previous_close
                percent_change = (change / previous_close) * 100

            return {
                "symbol": symbol,
                "current_price": current_price,
                "change": change,
                "percent_change": percent_change,
                "open": data['o'],
                "high": data['h'],
                "low": data['l'],
                "previous_close": previous_close,
                "timestamp": data['t']
            }
        else:
            logging.warning(f"No valid quote data for {symbol}: {data}")
            return None
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching quote for {symbol}: {e}")
        return None
    except ValueError as e:
        logging.error(f"Error parsing JSON response for quote {symbol}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while fetching quote for {symbol}: {e}")
        return None
    
def get_company_news(symbol, day_ago=1):
    """
    Fetch company news from Finnhub.io
    Get news for the last 'day_ago' days.
    """
    url = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={datetime.now().strftime('%Y-%m-%d')}&to={datetime.now().strftime('%Y-%m-%d')}&token={FINNHUB_API_KEY}"
    # Calculate the date 'day_ago' days ago
    from_date = (datetime.now() - timedelta(days=day_ago)).strftime('%Y-%m-%d')
    url_history = f"https://finnhub.io/api/v1/company-news?symbol={symbol}&from={from_date}&to={datetime.now().strftime('%Y-%m-%d')}&token={FINNHUB_API_KEY}"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        news_data_today = response.json()

        # If no news data for today, fetch historical news
        if isinstance(news_data_today, list) and news_data_today:
            # Finnhub News API fields:
            # category, datetime, headline, id, image, source, summary, url
            return news_data_today
        elif not news_data_today:
            response_history = requests.get(url_history)
            response_history.raise_for_status()
            news_data_history = response_history.json()
            if isinstance(news_data_history, list) and news_data_history:
                return news_data_history
            else:
                return None
        else:
            logging.warning(f"No valid news data for {symbol}: {news_data_today}")
            return None
    
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching news for {symbol}: {e}")
        return None
    except ValueError as e:
        logging.error(f"Error parsing JSON response for news {symbol}: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while fetching news for {symbol}: {e}")
        return None
    
if __name__ == "__main__":
    # Example usage
    print("Testing Finnhub API functions...")

    # Check if the API key is set
    if not FINNHUB_API_KEY or FINNHUB_API_KEY == config.FINNHUB_API_KEY:
        print("Please set your Finnhub API key in the config.py file.")
    else:
        # Test the stock price fetching
        aapl_quote = get_stock_data("AAPL")
        if aapl_quote:
            print(f"\nAAPL Quote: Current Price=${aapl_quote['current_price']:.2f}, Change=${aapl_quote['change']:.2f}, Percent Change={aapl_quote['percent_change']:.2f}%")
        else:
            print("\nFailed to get AAPL quote.")

        # Test the news fetching
        tsla_news = get_company_news("TSLA", day_ago=2)
        if tsla_news:
            print(f"\nTSLA News ({len(tsla_news)} articles):")
            for i, article in enumerate(tsla_news[:3]): # Limit to 3 articles
                print(f" {i+1}. {article['headline']} (Source: {article['source']}, URL: {article['url']})")
        else:
            print("\nNo TSLA news found or failed to get news.")    
