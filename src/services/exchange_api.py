"""
Exchange API Connector - Handles communication with cryptocurrency exchanges
Supports Binance, Coinbase, and other major exchanges
"""

import os
import time
import hmac
import hashlib
import json
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
from datetime import datetime

import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExchangeAPI:
    """Base class for exchange API connectors"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'CryptoTradingBot/1.0'
        })
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        raise NotImplementedError
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker information for a symbol"""
        raise NotImplementedError
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> Optional[Dict]:
        """Place a trading order"""
        raise NotImplementedError
    
    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get order status"""
        raise NotImplementedError
    
    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Cancel an order"""
        raise NotImplementedError
    
    def get_open_orders(self, symbol: str = None) -> Optional[List[Dict]]:
        """Get open orders"""
        raise NotImplementedError

class BinanceAPI(ExchangeAPI):
    """Binance API connector with support for spot trading"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        super().__init__(api_key, api_secret, testnet)
        
        if testnet:
            self.base_url = "https://testnet.binance.vision"
        else:
            self.base_url = "https://api.binance.com"
        
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key
        })
    
    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC SHA256 signature for Binance API"""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Optional[Dict]:
        """Make HTTP request to Binance API"""
        if params is None:
            params = {}
        
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params)
            elif method == 'POST':
                response = self.session.post(url, params=params)
            elif method == 'DELETE':
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Binance API request failed: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {str(e)}")
            return None
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        return self._make_request('GET', '/api/v3/account', signed=True)
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get 24hr ticker price change statistics"""
        params = {'symbol': symbol}
        return self._make_request('GET', '/api/v3/ticker/24hr', params)
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        params = {'symbol': symbol}
        result = self._make_request('GET', '/api/v3/ticker/price', params)
        if result:
            return float(result['price'])
        return None
    
    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[List[List]]:
        """Get kline/candlestick data"""
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        return self._make_request('GET', '/api/v3/klines', params)
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None, stop_price: float = None) -> Optional[Dict]:
        """Place a trading order"""
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': order_type.upper(),
            'quantity': str(quantity)
        }
        
        if order_type.upper() == 'LIMIT':
            if price is None:
                raise ValueError("Price is required for LIMIT orders")
            params['price'] = str(price)
            params['timeInForce'] = 'GTC'  # Good Till Cancelled
        
        if order_type.upper() == 'STOP_LOSS_LIMIT':
            if price is None or stop_price is None:
                raise ValueError("Price and stopPrice are required for STOP_LOSS_LIMIT orders")
            params['price'] = str(price)
            params['stopPrice'] = str(stop_price)
            params['timeInForce'] = 'GTC'
        
        return self._make_request('POST', '/api/v3/order', params, signed=True)
    
    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get order status"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return self._make_request('GET', '/api/v3/order', params, signed=True)
    
    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Cancel an order"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return self._make_request('DELETE', '/api/v3/order', params, signed=True)
    
    def get_open_orders(self, symbol: str = None) -> Optional[List[Dict]]:
        """Get all open orders"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._make_request('GET', '/api/v3/openOrders', params, signed=True)
    
    def get_order_book(self, symbol: str, limit: int = 100) -> Optional[Dict]:
        """Get order book depth"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self._make_request('GET', '/api/v3/depth', params)
    
    def get_exchange_info(self) -> Optional[Dict]:
        """Get exchange trading rules and symbol information"""
        return self._make_request('GET', '/api/v3/exchangeInfo')

class CoinbaseAPI(ExchangeAPI):
    """Coinbase Advanced Trade API connector"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        super().__init__(api_key, api_secret, testnet)
        
        if testnet:
            self.base_url = "https://api-public.sandbox.exchange.coinbase.com"
        else:
            self.base_url = "https://api.exchange.coinbase.com"
        
        self.session.headers.update({
            'CB-ACCESS-KEY': self.api_key
        })
    
    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = '') -> str:
        """Generate signature for Coinbase API"""
        message = timestamp + method + path + body
        return hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _make_request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Optional[Dict]:
        """Make HTTP request to Coinbase API"""
        timestamp = str(time.time())
        body = json.dumps(data) if data else ''
        
        signature = self._generate_signature(timestamp, method, endpoint, body)
        
        headers = {
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-SIGN': signature
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, headers=headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Coinbase API request failed: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {str(e)}")
            return None
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        return self._make_request('GET', '/accounts')
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get ticker information"""
        # Convert symbol format (BTCUSDT -> BTC-USD)
        if symbol.endswith('USDT'):
            symbol = symbol[:-4] + '-USD'
        return self._make_request('GET', f'/products/{symbol}/ticker')
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> Optional[Dict]:
        """Place a trading order"""
        # Convert symbol format
        if symbol.endswith('USDT'):
            symbol = symbol[:-4] + '-USD'
        
        data = {
            'product_id': symbol,
            'side': side.lower(),
            'type': order_type.lower(),
            'size': str(quantity)
        }
        
        if order_type.lower() == 'limit':
            if price is None:
                raise ValueError("Price is required for limit orders")
            data['price'] = str(price)
        
        return self._make_request('POST', '/orders', data=data)
    
    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get order status"""
        return self._make_request('GET', f'/orders/{order_id}')
    
    def cancel_order(self, order_id: str) -> Optional[Dict]:
        """Cancel an order"""
        return self._make_request('DELETE', f'/orders/{order_id}')
    
    def get_open_orders(self, symbol: str = None) -> Optional[List[Dict]]:
        """Get open orders"""
        params = {'status': 'open'}
        if symbol:
            if symbol.endswith('USDT'):
                symbol = symbol[:-4] + '-USD'
            params['product_id'] = symbol
        return self._make_request('GET', '/orders', params)

class ExchangeManager:
    """Manages multiple exchange connections and provides unified interface"""
    
    def __init__(self):
        self.exchanges = {}
        self.primary_exchange = None
        self._initialize_exchanges()
    
    def _initialize_exchanges(self):
        """Initialize exchange connections based on environment variables"""
        # Binance
        binance_key = os.getenv('BINANCE_API_KEY')
        binance_secret = os.getenv('BINANCE_API_SECRET')
        if binance_key and binance_secret:
            self.exchanges['binance'] = BinanceAPI(binance_key, binance_secret, testnet=True)
            if not self.primary_exchange:
                self.primary_exchange = 'binance'
            logger.info("Binance API initialized")
        
        # Coinbase
        coinbase_key = os.getenv('COINBASE_API_KEY')
        coinbase_secret = os.getenv('COINBASE_API_SECRET')
        if coinbase_key and coinbase_secret:
            self.exchanges['coinbase'] = CoinbaseAPI(coinbase_key, coinbase_secret, testnet=True)
            if not self.primary_exchange:
                self.primary_exchange = 'coinbase'
            logger.info("Coinbase API initialized")
    
    def get_exchange(self, exchange_name: str = None) -> Optional[ExchangeAPI]:
        """Get exchange API instance"""
        if exchange_name is None:
            exchange_name = self.primary_exchange
        
        return self.exchanges.get(exchange_name)
    
    def get_account_info(self, exchange_name: str = None) -> Optional[Dict]:
        """Get account info from specified exchange"""
        exchange = self.get_exchange(exchange_name)
        if exchange:
            return exchange.get_account_info()
        return None
    
    def get_ticker(self, symbol: str, exchange_name: str = None) -> Optional[Dict]:
        """Get ticker from specified exchange"""
        exchange = self.get_exchange(exchange_name)
        if exchange:
            return exchange.get_ticker(symbol)
        return None
    
    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, 
                   price: float = None, exchange_name: str = None) -> Optional[Dict]:
        """Place order on specified exchange"""
        exchange = self.get_exchange(exchange_name)
        if exchange:
            return exchange.place_order(symbol, side, order_type, quantity, price)
        return None
    
    def get_best_price(self, symbol: str) -> Optional[Tuple[str, float]]:
        """Get best price across all connected exchanges"""
        best_price = None
        best_exchange = None
        
        for exchange_name, exchange in self.exchanges.items():
            try:
                if hasattr(exchange, 'get_current_price'):
                    price = exchange.get_current_price(symbol)
                    if price and (best_price is None or price < best_price):
                        best_price = price
                        best_exchange = exchange_name
            except Exception as e:
                logger.warning(f"Failed to get price from {exchange_name}: {str(e)}")
        
        return (best_exchange, best_price) if best_price else None
    
    def validate_symbol(self, symbol: str, exchange_name: str = None) -> bool:
        """Validate if symbol is supported on exchange"""
        exchange = self.get_exchange(exchange_name)
        if not exchange:
            return False
        
        try:
            ticker = exchange.get_ticker(symbol)
            return ticker is not None
        except Exception:
            return False
    
    def get_trading_fees(self, exchange_name: str = None) -> Dict:
        """Get trading fees for exchange"""
        # Default fee structures
        fee_structures = {
            'binance': {
                'maker': 0.001,  # 0.1%
                'taker': 0.001,  # 0.1%
                'withdrawal': 'variable'
            },
            'coinbase': {
                'maker': 0.005,  # 0.5%
                'taker': 0.005,  # 0.5%
                'withdrawal': 'variable'
            }
        }
        
        if exchange_name is None:
            exchange_name = self.primary_exchange
        
        return fee_structures.get(exchange_name, {
            'maker': 0.002,  # 0.2% default
            'taker': 0.002,  # 0.2% default
            'withdrawal': 'variable'
        })

# Rate limiting decorator
class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls: int, time_window: int):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            now = time.time()
            # Remove old calls outside the time window
            self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
            
            if len(self.calls) >= self.max_calls:
                sleep_time = self.time_window - (now - self.calls[0])
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
            
            self.calls.append(now)
            return func(*args, **kwargs)
        return wrapper

# Apply rate limiting to exchange methods
def apply_rate_limits(exchange_class):
    """Apply rate limiting to exchange API methods"""
    # Binance: 1200 requests per minute
    if exchange_class.__name__ == 'BinanceAPI':
        rate_limiter = RateLimiter(max_calls=20, time_window=60)  # Conservative limit
        for method_name in ['get_ticker', 'place_order', 'get_order_status', 'cancel_order']:
            if hasattr(exchange_class, method_name):
                setattr(exchange_class, method_name, rate_limiter(getattr(exchange_class, method_name)))
    
    return exchange_class

# Apply rate limiting
BinanceAPI = apply_rate_limits(BinanceAPI)
CoinbaseAPI = apply_rate_limits(CoinbaseAPI)

