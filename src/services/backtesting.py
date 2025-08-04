"""
Backtesting and Simulation Framework
Allows testing trading strategies against historical data
"""

import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import matplotlib.pyplot as plt
import seaborn as sns

from src.services.trading_engine import TradingEngine
from src.services.exchange_api import ExchangeManager
from src.models.trading import db, Account, Trade, Position, AIAnalysis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BacktestResult:
    """Results from a backtest run"""
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[Dict]
    equity_curve: List[Dict]
    metrics: Dict

@dataclass
class Trade:
    """Individual trade record for backtesting"""
    timestamp: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    value: float
    commission: float
    pnl: float = 0.0
    cumulative_pnl: float = 0.0

class HistoricalDataManager:
    """Manages historical market data for backtesting"""
    
    def __init__(self):
        self.data_cache = {}
        self.exchange_manager = ExchangeManager()
    
    def get_historical_data(self, symbol: str, start_date: datetime, end_date: datetime, 
                          interval: str = '1h') -> Optional[pd.DataFrame]:
        """Get historical OHLCV data for backtesting"""
        cache_key = f"{symbol}_{interval}_{start_date.date()}_{end_date.date()}"
        
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        try:
            # Try to get data from exchange API
            exchange = self.exchange_manager.get_exchange('binance')
            if exchange:
                # Calculate number of periods needed
                if interval == '1h':
                    periods = int((end_date - start_date).total_seconds() / 3600)
                elif interval == '1d':
                    periods = (end_date - start_date).days
                else:
                    periods = 1000  # Default limit
                
                periods = min(periods, 1000)  # API limit
                
                klines = exchange.get_klines(symbol, interval, limit=periods)
                if klines:
                    df = self._parse_klines_data(klines)
                    self.data_cache[cache_key] = df
                    return df
            
            # Fallback: Generate synthetic data for testing
            logger.warning(f"Using synthetic data for {symbol}")
            return self._generate_synthetic_data(symbol, start_date, end_date, interval)
            
        except Exception as e:
            logger.error(f"Error getting historical data: {str(e)}")
            return self._generate_synthetic_data(symbol, start_date, end_date, interval)
    
    def _parse_klines_data(self, klines: List[List]) -> pd.DataFrame:
        """Parse klines data from exchange API"""
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        # Convert to proper types
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        df.set_index('timestamp', inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']]
    
    def _generate_synthetic_data(self, symbol: str, start_date: datetime, 
                               end_date: datetime, interval: str) -> pd.DataFrame:
        """Generate synthetic price data for testing"""
        # Calculate time delta
        if interval == '1h':
            freq = 'H'
        elif interval == '1d':
            freq = 'D'
        else:
            freq = 'H'
        
        # Create date range
        dates = pd.date_range(start=start_date, end=end_date, freq=freq)
        
        # Generate realistic price movement
        np.random.seed(42)  # For reproducible results
        
        # Starting price based on symbol
        if 'BTC' in symbol:
            base_price = 45000
        elif 'ETH' in symbol:
            base_price = 3000
        else:
            base_price = 100
        
        # Generate random walk with trend
        returns = np.random.normal(0.0001, 0.02, len(dates))  # Small positive drift
        prices = [base_price]
        
        for ret in returns[1:]:
            new_price = prices[-1] * (1 + ret)
            prices.append(new_price)
        
        # Create OHLCV data
        df = pd.DataFrame(index=dates)
        df['close'] = prices
        df['open'] = df['close'].shift(1).fillna(df['close'].iloc[0])
        
        # Generate high/low based on volatility
        volatility = np.random.uniform(0.005, 0.03, len(df))
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + volatility)
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - volatility)
        
        # Generate volume
        df['volume'] = np.random.uniform(1000000, 10000000, len(df))
        
        return df

class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self):
        self.data_manager = HistoricalDataManager()
        self.trading_engine = TradingEngine()
        
    def run_backtest(self, strategy_config: Dict, start_date: datetime, 
                    end_date: datetime, initial_balance: float = 100.0) -> BacktestResult:
        """Run a complete backtest"""
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        
        # Initialize backtest state
        balance = initial_balance
        positions = {}
        trades = []
        equity_curve = []
        
        # Get historical data
        symbol = strategy_config.get('symbol', 'BTCUSDT')
        interval = strategy_config.get('interval', '1h')
        
        data = self.data_manager.get_historical_data(symbol, start_date, end_date, interval)
        if data is None or data.empty:
            raise ValueError(f"No historical data available for {symbol}")
        
        logger.info(f"Backtesting with {len(data)} data points")
        
        # Simulate trading
        for timestamp, row in data.iterrows():
            current_price = row['close']
            
            # Update equity curve
            portfolio_value = self._calculate_portfolio_value(balance, positions, current_price)
            equity_curve.append({
                'timestamp': timestamp,
                'balance': balance,
                'portfolio_value': portfolio_value,
                'price': current_price
            })
            
            # Generate trading signal (simplified for backtesting)
            signal = self._generate_backtest_signal(row, data.loc[:timestamp], strategy_config)
            
            if signal and signal['action'] in ['BUY', 'SELL']:
                # Execute trade
                trade_result = self._execute_backtest_trade(
                    signal, timestamp, current_price, balance, positions, strategy_config
                )
                
                if trade_result:
                    trades.append(trade_result)
                    balance = trade_result['new_balance']
                    positions = trade_result['new_positions']
        
        # Calculate final metrics
        final_balance = self._calculate_portfolio_value(balance, positions, data.iloc[-1]['close'])
        
        return self._calculate_backtest_metrics(
            trades, equity_curve, initial_balance, final_balance, start_date, end_date
        )
    
    def _generate_backtest_signal(self, current_data: pd.Series, historical_data: pd.DataFrame, 
                                config: Dict) -> Optional[Dict]:
        """Generate trading signal for backtesting"""
        try:
            # Simple technical analysis for backtesting
            if len(historical_data) < 20:
                return None
            
            # Calculate indicators
            close_prices = historical_data['close']
            sma_20 = close_prices.rolling(20).mean().iloc[-1]
            sma_50 = close_prices.rolling(50).mean().iloc[-1] if len(close_prices) >= 50 else sma_20
            
            current_price = current_data['close']
            
            # Simple moving average crossover strategy
            if current_price > sma_20 and sma_20 > sma_50:
                return {
                    'action': 'BUY',
                    'confidence': 75,
                    'entry_price': current_price,
                    'stop_loss': current_price * 0.98,  # 2% stop loss
                    'take_profit': current_price * 1.04,  # 4% take profit
                    'reasoning': 'Price above SMA20, SMA20 above SMA50'
                }
            elif current_price < sma_20 and sma_20 < sma_50:
                return {
                    'action': 'SELL',
                    'confidence': 75,
                    'entry_price': current_price,
                    'stop_loss': current_price * 1.02,  # 2% stop loss
                    'take_profit': current_price * 0.96,  # 4% take profit
                    'reasoning': 'Price below SMA20, SMA20 below SMA50'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating backtest signal: {str(e)}")
            return None
    
    def _execute_backtest_trade(self, signal: Dict, timestamp: datetime, price: float,
                              balance: float, positions: Dict, config: Dict) -> Optional[Dict]:
        """Execute a trade in the backtest"""
        try:
            symbol = config.get('symbol', 'BTCUSDT')
            risk_percentage = config.get('risk_percentage', 1.0)
            commission_rate = config.get('commission_rate', 0.001)  # 0.1%
            
            # Calculate position size
            risk_amount = balance * (risk_percentage / 100)
            stop_loss = signal.get('stop_loss', price * 0.98)
            price_risk = abs(price - stop_loss)
            
            if price_risk <= 0:
                return None
            
            quantity = risk_amount / price_risk
            position_value = quantity * price
            
            # Check if we have enough balance
            if position_value > balance * 0.95:  # Leave 5% buffer
                quantity = (balance * 0.95) / price
                position_value = quantity * price
            
            commission = position_value * commission_rate
            
            if signal['action'] == 'BUY':
                if balance < position_value + commission:
                    return None  # Insufficient funds
                
                new_balance = balance - position_value - commission
                positions[symbol] = {
                    'side': 'LONG',
                    'quantity': quantity,
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': signal.get('take_profit', price * 1.04)
                }
                
                return {
                    'timestamp': timestamp,
                    'symbol': symbol,
                    'side': 'BUY',
                    'quantity': quantity,
                    'price': price,
                    'value': position_value,
                    'commission': commission,
                    'new_balance': new_balance,
                    'new_positions': positions.copy()
                }
            
            elif signal['action'] == 'SELL' and symbol in positions:
                # Close existing position
                position = positions[symbol]
                if position['side'] == 'LONG':
                    sell_value = position['quantity'] * price
                    sell_commission = sell_value * commission_rate
                    
                    # Calculate P&L
                    buy_value = position['quantity'] * position['entry_price']
                    pnl = sell_value - buy_value - commission - sell_commission
                    
                    new_balance = balance + sell_value - sell_commission
                    del positions[symbol]
                    
                    return {
                        'timestamp': timestamp,
                        'symbol': symbol,
                        'side': 'SELL',
                        'quantity': position['quantity'],
                        'price': price,
                        'value': sell_value,
                        'commission': sell_commission,
                        'pnl': pnl,
                        'new_balance': new_balance,
                        'new_positions': positions.copy()
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing backtest trade: {str(e)}")
            return None
    
    def _calculate_portfolio_value(self, balance: float, positions: Dict, current_price: float) -> float:
        """Calculate total portfolio value"""
        portfolio_value = balance
        
        for symbol, position in positions.items():
            if position['side'] == 'LONG':
                position_value = position['quantity'] * current_price
                portfolio_value += position_value
        
        return portfolio_value
    
    def _calculate_backtest_metrics(self, trades: List[Dict], equity_curve: List[Dict],
                                  initial_balance: float, final_balance: float,
                                  start_date: datetime, end_date: datetime) -> BacktestResult:
        """Calculate comprehensive backtest metrics"""
        
        # Basic metrics
        total_return = ((final_balance - initial_balance) / initial_balance) * 100
        total_trades = len([t for t in trades if 'pnl' in t])
        
        # Trade analysis
        profitable_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        
        winning_trades = len(profitable_trades)
        losing_count = len(losing_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Profit factor
        gross_profit = sum(t['pnl'] for t in profitable_trades)
        gross_loss = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        # Maximum drawdown
        portfolio_values = [eq['portfolio_value'] for eq in equity_curve]
        peak = portfolio_values[0]
        max_drawdown = 0
        
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = ((peak - value) / peak) * 100
            max_drawdown = max(max_drawdown, drawdown)
        
        # Sharpe ratio (simplified)
        returns = []
        for i in range(1, len(portfolio_values)):
            ret = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1]
            returns.append(ret)
        
        if returns:
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Additional metrics
        metrics = {
            'total_commission': sum(t.get('commission', 0) for t in trades),
            'average_win': gross_profit / winning_trades if winning_trades > 0 else 0,
            'average_loss': gross_loss / losing_count if losing_count > 0 else 0,
            'largest_win': max((t.get('pnl', 0) for t in profitable_trades), default=0),
            'largest_loss': min((t.get('pnl', 0) for t in losing_trades), default=0),
            'consecutive_wins': self._calculate_consecutive_wins(trades),
            'consecutive_losses': self._calculate_consecutive_losses(trades),
            'trading_period_days': (end_date - start_date).days,
            'trades_per_day': total_trades / max((end_date - start_date).days, 1)
        }
        
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=final_balance,
            total_return=total_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_count,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics
        )
    
    def _calculate_consecutive_wins(self, trades: List[Dict]) -> int:
        """Calculate maximum consecutive winning trades"""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in trades:
            if trade.get('pnl', 0) > 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_consecutive_losses(self, trades: List[Dict]) -> int:
        """Calculate maximum consecutive losing trades"""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in trades:
            if trade.get('pnl', 0) < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive

class BacktestVisualizer:
    """Creates visualizations for backtest results"""
    
    def __init__(self):
        plt.style.use('seaborn-v0_8')
        self.colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
    
    def create_backtest_report(self, result: BacktestResult, output_dir: str = 'backtest_results'):
        """Create comprehensive backtest report with visualizations"""
        os.makedirs(output_dir, exist_ok=True)
        
        # Create multiple charts
        self._plot_equity_curve(result, output_dir)
        self._plot_drawdown(result, output_dir)
        self._plot_trade_distribution(result, output_dir)
        self._plot_monthly_returns(result, output_dir)
        
        # Generate HTML report
        self._generate_html_report(result, output_dir)
        
        logger.info(f"Backtest report generated in {output_dir}")
    
    def _plot_equity_curve(self, result: BacktestResult, output_dir: str):
        """Plot equity curve"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # Equity curve
        timestamps = [eq['timestamp'] for eq in result.equity_curve]
        portfolio_values = [eq['portfolio_value'] for eq in result.equity_curve]
        prices = [eq['price'] for eq in result.equity_curve]
        
        ax1.plot(timestamps, portfolio_values, color=self.colors[0], linewidth=2, label='Portfolio Value')
        ax1.axhline(y=result.initial_balance, color='red', linestyle='--', alpha=0.7, label='Initial Balance')
        ax1.set_title('Portfolio Equity Curve', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Portfolio Value ($)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Price chart
        ax2.plot(timestamps, prices, color=self.colors[1], linewidth=1, label='Price')
        ax2.set_title('Asset Price', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Price ($)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/equity_curve.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_drawdown(self, result: BacktestResult, output_dir: str):
        """Plot drawdown chart"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Calculate drawdown
        portfolio_values = [eq['portfolio_value'] for eq in result.equity_curve]
        timestamps = [eq['timestamp'] for eq in result.equity_curve]
        
        peak = portfolio_values[0]
        drawdowns = []
        
        for value in portfolio_values:
            if value > peak:
                peak = value
            drawdown = ((peak - value) / peak) * 100
            drawdowns.append(-drawdown)  # Negative for visualization
        
        ax.fill_between(timestamps, drawdowns, 0, color=self.colors[3], alpha=0.7, label='Drawdown')
        ax.plot(timestamps, drawdowns, color=self.colors[3], linewidth=1)
        ax.set_title('Portfolio Drawdown', fontsize=14, fontweight='bold')
        ax.set_xlabel('Date')
        ax.set_ylabel('Drawdown (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/drawdown.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_trade_distribution(self, result: BacktestResult, output_dir: str):
        """Plot trade P&L distribution"""
        trades_with_pnl = [t for t in result.trades if 'pnl' in t]
        if not trades_with_pnl:
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # P&L histogram
        pnls = [t['pnl'] for t in trades_with_pnl]
        ax1.hist(pnls, bins=20, color=self.colors[0], alpha=0.7, edgecolor='black')
        ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7)
        ax1.set_title('Trade P&L Distribution', fontsize=14, fontweight='bold')
        ax1.set_xlabel('P&L ($)')
        ax1.set_ylabel('Frequency')
        ax1.grid(True, alpha=0.3)
        
        # Win/Loss pie chart
        winning_trades = len([p for p in pnls if p > 0])
        losing_trades = len([p for p in pnls if p < 0])
        
        labels = ['Winning Trades', 'Losing Trades']
        sizes = [winning_trades, losing_trades]
        colors = [self.colors[0], self.colors[3]]
        
        ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax2.set_title('Win/Loss Ratio', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/trade_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_monthly_returns(self, result: BacktestResult, output_dir: str):
        """Plot monthly returns"""
        if len(result.equity_curve) < 30:  # Not enough data for monthly analysis
            return
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(result.equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        # Resample to monthly
        monthly_values = df['portfolio_value'].resample('M').last()
        monthly_returns = monthly_values.pct_change().dropna() * 100
        
        colors = [self.colors[0] if ret >= 0 else self.colors[3] for ret in monthly_returns]
        
        ax.bar(range(len(monthly_returns)), monthly_returns, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax.set_title('Monthly Returns', fontsize=14, fontweight='bold')
        ax.set_xlabel('Month')
        ax.set_ylabel('Return (%)')
        ax.set_xticks(range(len(monthly_returns)))
        ax.set_xticklabels([d.strftime('%Y-%m') for d in monthly_returns.index], rotation=45)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/monthly_returns.png', dpi=300, bbox_inches='tight')
        plt.close()
    
    def _generate_html_report(self, result: BacktestResult, output_dir: str):
        """Generate HTML report"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Backtest Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
                .metric-card {{ background: #f5f5f5; padding: 15px; border-radius: 8px; text-align: center; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #2E86AB; }}
                .metric-label {{ font-size: 14px; color: #666; }}
                .chart {{ text-align: center; margin: 30px 0; }}
                .chart img {{ max-width: 100%; height: auto; }}
                .positive {{ color: #27ae60; }}
                .negative {{ color: #e74c3c; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Cryptocurrency Trading Bot Backtest Report</h1>
                <p>Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}</p>
            </div>
            
            <div class="metrics">
                <div class="metric-card">
                    <div class="metric-value {'positive' if result.total_return >= 0 else 'negative'}">{result.total_return:.2f}%</div>
                    <div class="metric-label">Total Return</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">${result.final_balance:.2f}</div>
                    <div class="metric-label">Final Balance</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.win_rate:.1f}%</div>
                    <div class="metric-label">Win Rate</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.profit_factor:.2f}</div>
                    <div class="metric-label">Profit Factor</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.max_drawdown:.2f}%</div>
                    <div class="metric-label">Max Drawdown</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.sharpe_ratio:.2f}</div>
                    <div class="metric-label">Sharpe Ratio</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.total_trades}</div>
                    <div class="metric-label">Total Trades</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{result.metrics['trades_per_day']:.2f}</div>
                    <div class="metric-label">Trades/Day</div>
                </div>
            </div>
            
            <div class="chart">
                <h2>Portfolio Performance</h2>
                <img src="equity_curve.png" alt="Equity Curve">
            </div>
            
            <div class="chart">
                <h2>Risk Analysis</h2>
                <img src="drawdown.png" alt="Drawdown Chart">
            </div>
            
            <div class="chart">
                <h2>Trade Analysis</h2>
                <img src="trade_distribution.png" alt="Trade Distribution">
            </div>
            
            <div class="chart">
                <h2>Monthly Performance</h2>
                <img src="monthly_returns.png" alt="Monthly Returns">
            </div>
            
            <div style="margin-top: 40px;">
                <h2>Additional Metrics</h2>
                <ul>
                    <li>Trading Period: {result.metrics['trading_period_days']} days</li>
                    <li>Total Commission: ${result.metrics['total_commission']:.2f}</li>
                    <li>Average Win: ${result.metrics['average_win']:.2f}</li>
                    <li>Average Loss: ${result.metrics['average_loss']:.2f}</li>
                    <li>Largest Win: ${result.metrics['largest_win']:.2f}</li>
                    <li>Largest Loss: ${result.metrics['largest_loss']:.2f}</li>
                    <li>Max Consecutive Wins: {result.metrics['consecutive_wins']}</li>
                    <li>Max Consecutive Losses: {result.metrics['consecutive_losses']}</li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        with open(f'{output_dir}/backtest_report.html', 'w') as f:
            f.write(html_content)

# Example usage and testing functions
def run_sample_backtest():
    """Run a sample backtest for demonstration"""
    engine = BacktestEngine()
    visualizer = BacktestVisualizer()
    
    # Configuration
    strategy_config = {
        'symbol': 'BTCUSDT',
        'interval': '1h',
        'risk_percentage': 1.0,
        'commission_rate': 0.001
    }
    
    # Date range (last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    try:
        # Run backtest
        result = engine.run_backtest(strategy_config, start_date, end_date, 100.0)
        
        # Create visualizations
        visualizer.create_backtest_report(result)
        
        print(f"Backtest completed successfully!")
        print(f"Total Return: {result.total_return:.2f}%")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print(f"Max Drawdown: {result.max_drawdown:.2f}%")
        print(f"Report saved to: backtest_results/backtest_report.html")
        
        return result
        
    except Exception as e:
        logger.error(f"Backtest failed: {str(e)}")
        return None

if __name__ == "__main__":
    # Run sample backtest
    run_sample_backtest()

