"""
Trading Bot API Routes
Provides REST API endpoints for trading bot functionality
"""

import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import desc

from src.models.trading import db, Account, Trade, Position, AIAnalysis, MarketData, RiskEvent
from src.services.trading_engine import TradingEngine
from src.services.exchange_api import ExchangeManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create blueprint
trading_bp = Blueprint('trading', __name__)

# Initialize services
trading_engine = TradingEngine()
exchange_manager = ExchangeManager()

@trading_bp.route('/accounts', methods=['GET'])
def get_accounts():
    """Get all trading accounts"""
    try:
        accounts = Account.query.all()
        return jsonify({
            'success': True,
            'accounts': [account.to_dict() for account in accounts]
        })
    except Exception as e:
        logger.error(f"Error getting accounts: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts', methods=['POST'])
def create_account():
    """Create a new trading account"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'exchange', 'api_key', 'api_secret']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Create new account
        account = Account(
            name=data['name'],
            exchange=data['exchange'],
            api_key_hash=data['api_key'][:10] + '...',  # Store only partial key for security
            balance=data.get('balance', 100.0),
            initial_balance=data.get('balance', 100.0),
            risk_percentage=data.get('risk_percentage', 1.0),
            max_positions=data.get('max_positions', 3)
        )
        
        db.session.add(account)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'account': account.to_dict()
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating account: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>', methods=['GET'])
def get_account(account_id):
    """Get specific account details"""
    try:
        account = Account.query.get_or_404(account_id)
        
        # Get account statistics
        total_trades = Trade.query.filter_by(account_id=account_id).count()
        open_positions = Position.query.filter_by(account_id=account_id, status='open').count()
        
        # Calculate P&L
        filled_trades = Trade.query.filter_by(account_id=account_id, status='filled').all()
        total_pnl = 0  # Simplified - would need proper P&L calculation
        
        account_data = account.to_dict()
        account_data.update({
            'total_trades': total_trades,
            'open_positions': open_positions,
            'total_pnl': total_pnl,
            'win_rate': 0  # Would calculate from trade history
        })
        
        return jsonify({
            'success': True,
            'account': account_data
        })
        
    except Exception as e:
        logger.error(f"Error getting account {account_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/analyze', methods=['POST'])
def analyze_market(account_id):
    """Analyze market and generate trading signal"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTCUSDT')
        
        # Validate account exists
        account = Account.query.get_or_404(account_id)
        
        # Generate trading signal
        signal = trading_engine.analyze_market_and_generate_signal(account_id, symbol)
        
        if signal:
            return jsonify({
                'success': True,
                'signal': signal
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate trading signal'
            }), 500
            
    except Exception as e:
        logger.error(f"Error analyzing market: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/trades', methods=['GET'])
def get_trades(account_id):
    """Get trading history for account"""
    try:
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        status = request.args.get('status')
        symbol = request.args.get('symbol')
        
        # Build query
        query = Trade.query.filter_by(account_id=account_id)
        
        if status:
            query = query.filter_by(status=status)
        if symbol:
            query = query.filter_by(symbol=symbol)
        
        trades = query.order_by(desc(Trade.created_at)).limit(limit).all()
        
        return jsonify({
            'success': True,
            'trades': [trade.to_dict() for trade in trades]
        })
        
    except Exception as e:
        logger.error(f"Error getting trades: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/positions', methods=['GET'])
def get_positions(account_id):
    """Get open positions for account"""
    try:
        positions = Position.query.filter_by(account_id=account_id, status='open').all()
        
        # Update current prices and P&L
        for position in positions:
            # Get current price from exchange
            ticker = exchange_manager.get_ticker(position.symbol)
            if ticker:
                current_price = float(ticker.get('price', position.current_price))
                position.current_price = current_price
                position.unrealized_pnl = position.calculate_pnl(current_price)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'positions': [position.to_dict() for position in positions]
        })
        
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/execute-trade', methods=['POST'])
def execute_trade(account_id):
    """Execute a trading signal"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['symbol', 'side', 'quantity', 'price']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        account = Account.query.get_or_404(account_id)
        
        # Create trade record
        trade = Trade(
            account_id=account_id,
            symbol=data['symbol'],
            side=data['side'],
            order_type=data.get('order_type', 'MARKET'),
            quantity=data['quantity'],
            price=data['price'],
            total_value=data['quantity'] * data['price'],
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit')
        )
        
        db.session.add(trade)
        db.session.flush()  # Get trade ID
        
        # Execute trade on exchange (mock for now)
        exchange = exchange_manager.get_exchange(account.exchange)
        if exchange:
            try:
                order_result = exchange.place_order(
                    symbol=data['symbol'],
                    side=data['side'],
                    order_type=data.get('order_type', 'MARKET'),
                    quantity=data['quantity'],
                    price=data.get('price') if data.get('order_type') == 'LIMIT' else None
                )
                
                if order_result:
                    trade.exchange_order_id = str(order_result.get('orderId', ''))
                    trade.status = 'filled'  # Simplified - would check actual status
                    trade.executed_at = datetime.utcnow()
                    
                    # Create position if it's a buy order
                    if data['side'].upper() == 'BUY':
                        position = Position(
                            account_id=account_id,
                            symbol=data['symbol'],
                            side='LONG',
                            quantity=data['quantity'],
                            entry_price=data['price'],
                            current_price=data['price'],
                            stop_loss=data.get('stop_loss'),
                            take_profit=data.get('take_profit'),
                            entry_trade_id=trade.id
                        )
                        db.session.add(position)
                    
                    # Update account balance (simplified)
                    if data['side'].upper() == 'BUY':
                        account.balance -= trade.total_value
                    else:
                        account.balance += trade.total_value
                    
                else:
                    trade.status = 'failed'
                    
            except Exception as e:
                logger.error(f"Exchange execution failed: {str(e)}")
                trade.status = 'failed'
        else:
            # Mock execution for testing
            trade.status = 'filled'
            trade.executed_at = datetime.utcnow()
            trade.exchange_order_id = f"mock_{trade.id}"
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'trade': trade.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error executing trade: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/market-data/<symbol>', methods=['GET'])
def get_market_data(symbol):
    """Get market data for a symbol"""
    try:
        # Get data from exchange
        ticker = exchange_manager.get_ticker(symbol)
        
        if not ticker:
            return jsonify({'success': False, 'error': 'Failed to get market data'}), 404
        
        # Get historical data from database
        historical_data = MarketData.query.filter_by(
            symbol=symbol,
            timeframe='1h'
        ).order_by(desc(MarketData.timestamp)).limit(24).all()
        
        return jsonify({
            'success': True,
            'current': ticker,
            'historical': [data.to_dict() for data in historical_data]
        })
        
    except Exception as e:
        logger.error(f"Error getting market data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/ai-analysis', methods=['GET'])
def get_ai_analysis():
    """Get recent AI analysis results"""
    try:
        limit = request.args.get('limit', 10, type=int)
        symbol = request.args.get('symbol')
        
        query = AIAnalysis.query
        if symbol:
            query = query.filter_by(symbol=symbol)
        
        analyses = query.order_by(desc(AIAnalysis.created_at)).limit(limit).all()
        
        return jsonify({
            'success': True,
            'analyses': [analysis.to_dict() for analysis in analyses]
        })
        
    except Exception as e:
        logger.error(f"Error getting AI analysis: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/risk-events', methods=['GET'])
def get_risk_events():
    """Get risk management events"""
    try:
        limit = request.args.get('limit', 20, type=int)
        account_id = request.args.get('account_id', type=int)
        
        query = RiskEvent.query
        if account_id:
            query = query.filter_by(account_id=account_id)
        
        events = query.order_by(desc(RiskEvent.created_at)).limit(limit).all()
        
        return jsonify({
            'success': True,
            'events': [event.to_dict() for event in events]
        })
        
    except Exception as e:
        logger.error(f"Error getting risk events: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/system/status', methods=['GET'])
def get_system_status():
    """Get system status and health check"""
    try:
        # Check database connection
        db_status = True
        try:
            db.session.execute('SELECT 1')
        except Exception:
            db_status = False
        
        # Check exchange connections
        exchange_status = {}
        for exchange_name in exchange_manager.exchanges:
            try:
                exchange = exchange_manager.get_exchange(exchange_name)
                # Try to get ticker for BTC to test connection
                ticker = exchange.get_ticker('BTCUSDT')
                exchange_status[exchange_name] = ticker is not None
            except Exception:
                exchange_status[exchange_name] = False
        
        # Check AI service
        ai_status = trading_engine.deepseek_client is not None
        
        # Get system statistics
        total_accounts = Account.query.count()
        active_accounts = Account.query.filter_by(status='active').count()
        total_trades = Trade.query.count()
        open_positions = Position.query.filter_by(status='open').count()
        
        return jsonify({
            'success': True,
            'status': {
                'database': db_status,
                'exchanges': exchange_status,
                'ai_service': ai_status,
                'statistics': {
                    'total_accounts': total_accounts,
                    'active_accounts': active_accounts,
                    'total_trades': total_trades,
                    'open_positions': open_positions
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/start', methods=['POST'])
def start_trading(account_id):
    """Start automated trading for account"""
    try:
        account = Account.query.get_or_404(account_id)
        account.status = 'active'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Trading started for account {account.name}'
        })
        
    except Exception as e:
        logger.error(f"Error starting trading: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/stop', methods=['POST'])
def stop_trading(account_id):
    """Stop automated trading for account"""
    try:
        account = Account.query.get_or_404(account_id)
        account.status = 'stopped'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Trading stopped for account {account.name}'
        })
        
    except Exception as e:
        logger.error(f"Error stopping trading: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@trading_bp.route('/accounts/<int:account_id>/pause', methods=['POST'])
def pause_trading(account_id):
    """Pause automated trading for account"""
    try:
        account = Account.query.get_or_404(account_id)
        account.status = 'paused'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Trading paused for account {account.name}'
        })
        
    except Exception as e:
        logger.error(f"Error pausing trading: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Error handlers
@trading_bp.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'error': 'Resource not found'}), 404

@trading_bp.errorhandler(400)
def bad_request(error):
    return jsonify({'success': False, 'error': 'Bad request'}), 400

@trading_bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

