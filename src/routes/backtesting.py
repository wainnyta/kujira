"""
Backtesting API Routes
Provides REST API endpoints for backtesting functionality
"""

import logging
import os
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

from src.services.backtesting import BacktestEngine, BacktestVisualizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
backtesting_bp = Blueprint('backtesting', __name__)

# Initialize services
backtest_engine = BacktestEngine()
backtest_visualizer = BacktestVisualizer()

@backtesting_bp.route('/run', methods=['POST'])
def run_backtest():
    """Run a backtest with specified parameters"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Parse dates
        try:
            start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        except ValueError as e:
            return jsonify({'success': False, 'error': f'Invalid date format: {str(e)}'}), 400
        
        # Validate date range
        if start_date >= end_date:
            return jsonify({'success': False, 'error': 'Start date must be before end date'}), 400
        
        if (end_date - start_date).days > 365:
            return jsonify({'success': False, 'error': 'Maximum backtest period is 365 days'}), 400
        
        # Strategy configuration
        strategy_config = {
            'symbol': data['symbol'],
            'interval': data.get('interval', '1h'),
            'risk_percentage': data.get('risk_percentage', 1.0),
            'commission_rate': data.get('commission_rate', 0.001),
            'stop_loss_percentage': data.get('stop_loss_percentage', 2.0),
            'take_profit_percentage': data.get('take_profit_percentage', 4.0)
        }
        
        # Initial balance
        initial_balance = data.get('initial_balance', 100.0)
        
        # Run backtest
        logger.info(f"Starting backtest for {data['symbol']} from {start_date} to {end_date}")
        result = backtest_engine.run_backtest(strategy_config, start_date, end_date, initial_balance)
        
        if result:
            # Generate unique output directory
            output_dir = f"backtest_results/{data['symbol']}_{int(datetime.now().timestamp())}"
            
            # Create visualizations
            backtest_visualizer.create_backtest_report(result, output_dir)
            
            # Convert result to JSON-serializable format
            result_data = {
                'start_date': result.start_date.isoformat(),
                'end_date': result.end_date.isoformat(),
                'initial_balance': result.initial_balance,
                'final_balance': result.final_balance,
                'total_return': result.total_return,
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'win_rate': result.win_rate,
                'profit_factor': result.profit_factor,
                'max_drawdown': result.max_drawdown,
                'sharpe_ratio': result.sharpe_ratio,
                'metrics': result.metrics,
                'report_path': output_dir,
                'trades_count': len(result.trades),
                'equity_points': len(result.equity_curve)
            }
            
            return jsonify({
                'success': True,
                'result': result_data
            })
        else:
            return jsonify({'success': False, 'error': 'Backtest execution failed'}), 500
            
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/quick-test', methods=['POST'])
def quick_backtest():
    """Run a quick backtest with default parameters"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTCUSDT')
        days = data.get('days', 30)
        
        # Set date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Default strategy configuration
        strategy_config = {
            'symbol': symbol,
            'interval': '1h',
            'risk_percentage': 1.0,
            'commission_rate': 0.001
        }
        
        # Run backtest
        result = backtest_engine.run_backtest(strategy_config, start_date, end_date, 100.0)
        
        if result:
            # Return simplified result for quick testing
            return jsonify({
                'success': True,
                'result': {
                    'total_return': result.total_return,
                    'final_balance': result.final_balance,
                    'win_rate': result.win_rate,
                    'total_trades': result.total_trades,
                    'max_drawdown': result.max_drawdown,
                    'profit_factor': result.profit_factor
                }
            })
        else:
            return jsonify({'success': False, 'error': 'Quick backtest failed'}), 500
            
    except Exception as e:
        logger.error(f"Error running quick backtest: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/report/<path:report_path>')
def get_backtest_report(report_path):
    """Serve backtest report files"""
    try:
        # Secure the filename
        safe_path = secure_filename(report_path)
        file_path = os.path.join('backtest_results', safe_path)
        
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'success': False, 'error': 'Report file not found'}), 404
            
    except Exception as e:
        logger.error(f"Error serving report: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/strategies', methods=['GET'])
def get_available_strategies():
    """Get list of available backtesting strategies"""
    try:
        strategies = [
            {
                'id': 'sma_crossover',
                'name': 'Simple Moving Average Crossover',
                'description': 'Buy when price crosses above SMA20, sell when below',
                'parameters': {
                    'sma_short': {'type': 'int', 'default': 20, 'min': 5, 'max': 50},
                    'sma_long': {'type': 'int', 'default': 50, 'min': 20, 'max': 200}
                }
            },
            {
                'id': 'rsi_mean_reversion',
                'name': 'RSI Mean Reversion',
                'description': 'Buy when RSI < 30, sell when RSI > 70',
                'parameters': {
                    'rsi_period': {'type': 'int', 'default': 14, 'min': 7, 'max': 30},
                    'oversold_threshold': {'type': 'float', 'default': 30, 'min': 20, 'max': 40},
                    'overbought_threshold': {'type': 'float', 'default': 70, 'min': 60, 'max': 80}
                }
            },
            {
                'id': 'macd_momentum',
                'name': 'MACD Momentum',
                'description': 'Trade based on MACD line and signal line crossovers',
                'parameters': {
                    'fast_period': {'type': 'int', 'default': 12, 'min': 8, 'max': 20},
                    'slow_period': {'type': 'int', 'default': 26, 'min': 20, 'max': 40},
                    'signal_period': {'type': 'int', 'default': 9, 'min': 5, 'max': 15}
                }
            }
        ]
        
        return jsonify({
            'success': True,
            'strategies': strategies
        })
        
    except Exception as e:
        logger.error(f"Error getting strategies: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/symbols', methods=['GET'])
def get_available_symbols():
    """Get list of available trading symbols for backtesting"""
    try:
        symbols = [
            {'symbol': 'BTCUSDT', 'name': 'Bitcoin/USDT', 'category': 'Major'},
            {'symbol': 'ETHUSDT', 'name': 'Ethereum/USDT', 'category': 'Major'},
            {'symbol': 'BNBUSDT', 'name': 'Binance Coin/USDT', 'category': 'Major'},
            {'symbol': 'ADAUSDT', 'name': 'Cardano/USDT', 'category': 'Altcoin'},
            {'symbol': 'DOTUSDT', 'name': 'Polkadot/USDT', 'category': 'Altcoin'},
            {'symbol': 'LINKUSDT', 'name': 'Chainlink/USDT', 'category': 'Altcoin'},
            {'symbol': 'LTCUSDT', 'name': 'Litecoin/USDT', 'category': 'Major'},
            {'symbol': 'XRPUSDT', 'name': 'Ripple/USDT', 'category': 'Major'}
        ]
        
        return jsonify({
            'success': True,
            'symbols': symbols
        })
        
    except Exception as e:
        logger.error(f"Error getting symbols: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/optimize', methods=['POST'])
def optimize_strategy():
    """Run strategy optimization across multiple parameter combinations"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'start_date', 'end_date', 'strategy']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Parse dates
        start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        
        # Get parameter ranges
        param_ranges = data.get('parameter_ranges', {})
        
        # Run optimization (simplified version)
        optimization_results = []
        
        # Example: optimize risk percentage
        risk_percentages = param_ranges.get('risk_percentage', [0.5, 1.0, 1.5, 2.0])
        
        for risk_pct in risk_percentages:
            strategy_config = {
                'symbol': data['symbol'],
                'interval': data.get('interval', '1h'),
                'risk_percentage': risk_pct,
                'commission_rate': data.get('commission_rate', 0.001)
            }
            
            try:
                result = backtest_engine.run_backtest(
                    strategy_config, start_date, end_date, 
                    data.get('initial_balance', 100.0)
                )
                
                if result:
                    optimization_results.append({
                        'parameters': {'risk_percentage': risk_pct},
                        'total_return': result.total_return,
                        'win_rate': result.win_rate,
                        'max_drawdown': result.max_drawdown,
                        'profit_factor': result.profit_factor,
                        'sharpe_ratio': result.sharpe_ratio
                    })
            except Exception as e:
                logger.warning(f"Optimization run failed for risk_pct={risk_pct}: {str(e)}")
        
        # Sort by total return
        optimization_results.sort(key=lambda x: x['total_return'], reverse=True)
        
        return jsonify({
            'success': True,
            'optimization_results': optimization_results,
            'best_parameters': optimization_results[0]['parameters'] if optimization_results else None
        })
        
    except Exception as e:
        logger.error(f"Error running optimization: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/compare', methods=['POST'])
def compare_strategies():
    """Compare multiple strategies side by side"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'start_date', 'end_date', 'strategies']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Parse dates
        start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        
        comparison_results = []
        
        for strategy_data in data['strategies']:
            strategy_config = {
                'symbol': data['symbol'],
                'interval': data.get('interval', '1h'),
                'risk_percentage': strategy_data.get('risk_percentage', 1.0),
                'commission_rate': data.get('commission_rate', 0.001)
            }
            
            try:
                result = backtest_engine.run_backtest(
                    strategy_config, start_date, end_date,
                    data.get('initial_balance', 100.0)
                )
                
                if result:
                    comparison_results.append({
                        'strategy_name': strategy_data.get('name', 'Unnamed Strategy'),
                        'parameters': strategy_data,
                        'total_return': result.total_return,
                        'final_balance': result.final_balance,
                        'win_rate': result.win_rate,
                        'total_trades': result.total_trades,
                        'max_drawdown': result.max_drawdown,
                        'profit_factor': result.profit_factor,
                        'sharpe_ratio': result.sharpe_ratio
                    })
            except Exception as e:
                logger.warning(f"Strategy comparison failed: {str(e)}")
        
        return jsonify({
            'success': True,
            'comparison_results': comparison_results
        })
        
    except Exception as e:
        logger.error(f"Error comparing strategies: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@backtesting_bp.route('/history', methods=['GET'])
def get_backtest_history():
    """Get history of previous backtests"""
    try:
        # Get list of backtest result directories
        backtest_dir = 'backtest_results'
        if not os.path.exists(backtest_dir):
            return jsonify({'success': True, 'history': []})
        
        history = []
        for item in os.listdir(backtest_dir):
            item_path = os.path.join(backtest_dir, item)
            if os.path.isdir(item_path):
                # Check if report exists
                report_file = os.path.join(item_path, 'backtest_report.html')
                if os.path.exists(report_file):
                    # Extract info from directory name
                    parts = item.split('_')
                    if len(parts) >= 2:
                        symbol = parts[0]
                        timestamp = int(parts[1]) if parts[1].isdigit() else 0
                        
                        history.append({
                            'id': item,
                            'symbol': symbol,
                            'timestamp': timestamp,
                            'date': datetime.fromtimestamp(timestamp).isoformat() if timestamp else 'Unknown',
                            'report_url': f'/api/backtesting/report/{item}/backtest_report.html'
                        })
        
        # Sort by timestamp (newest first)
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        logger.error(f"Error getting backtest history: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Error handlers
@backtesting_bp.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Resource not found'}), 404

@backtesting_bp.errorhandler(400)
def bad_request(error):
    return jsonify({'success': False, 'error': 'Bad request'}), 400

@backtesting_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

