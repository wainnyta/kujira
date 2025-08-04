"""
Trading Bot Database Models
Defines the database schema for accounts, trades, AI analysis, and market data
"""

from src.models.user import db
from datetime import datetime
import json

class Account(db.Model):
    """User trading account information"""
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    exchange = db.Column(db.String(50), nullable=False)  # binance, coinbase, etc.
    api_key_hash = db.Column(db.String(255), nullable=False)
    balance = db.Column(db.Numeric(18, 8), default=100.0)
    initial_balance = db.Column(db.Numeric(18, 8), default=100.0)
    risk_percentage = db.Column(db.Numeric(5, 2), default=1.0)  # 1% default risk per trade
    max_positions = db.Column(db.Integer, default=3)
    status = db.Column(db.String(20), default='active')  # active, paused, stopped
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    trades = db.relationship('Trade', backref='account', lazy=True)
    positions = db.relationship('Position', backref='account', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'exchange': self.exchange,
            'balance': float(self.balance),
            'initial_balance': float(self.initial_balance),
            'risk_percentage': float(self.risk_percentage),
            'max_positions': self.max_positions,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

class Trade(db.Model):
    """Individual trade records"""
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)  # BTCUSDT, ETHUSDT, etc.
    side = db.Column(db.String(10), nullable=False)  # BUY, SELL
    order_type = db.Column(db.String(20), default='MARKET')  # MARKET, LIMIT, STOP_LOSS
    quantity = db.Column(db.Numeric(18, 8), nullable=False)
    price = db.Column(db.Numeric(18, 8), nullable=False)
    fee = db.Column(db.Numeric(18, 8), default=0)
    total_value = db.Column(db.Numeric(18, 8), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, filled, cancelled, failed
    exchange_order_id = db.Column(db.String(100))
    ai_analysis_id = db.Column(db.Integer, db.ForeignKey('ai_analysis.id'))
    stop_loss = db.Column(db.Numeric(18, 8))
    take_profit = db.Column(db.Numeric(18, 8))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type,
            'quantity': float(self.quantity),
            'price': float(self.price),
            'fee': float(self.fee),
            'total_value': float(self.total_value),
            'status': self.status,
            'exchange_order_id': self.exchange_order_id,
            'stop_loss': float(self.stop_loss) if self.stop_loss else None,
            'take_profit': float(self.take_profit) if self.take_profit else None,
            'created_at': self.created_at.isoformat(),
            'executed_at': self.executed_at.isoformat() if self.executed_at else None
        }

class Position(db.Model):
    """Current open positions"""
    __tablename__ = 'positions'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    symbol = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(10), nullable=False)  # LONG, SHORT
    quantity = db.Column(db.Numeric(18, 8), nullable=False)
    entry_price = db.Column(db.Numeric(18, 8), nullable=False)
    current_price = db.Column(db.Numeric(18, 8), nullable=False)
    unrealized_pnl = db.Column(db.Numeric(18, 8), default=0)
    stop_loss = db.Column(db.Numeric(18, 8))
    take_profit = db.Column(db.Numeric(18, 8))
    entry_trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'))
    status = db.Column(db.String(20), default='open')  # open, closed
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime)
    
    def calculate_pnl(self, current_price):
        """Calculate unrealized P&L"""
        if self.side == 'LONG':
            pnl = (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            pnl = (self.entry_price - current_price) * self.quantity
        return float(pnl)
    
    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'symbol': self.symbol,
            'side': self.side,
            'quantity': float(self.quantity),
            'entry_price': float(self.entry_price),
            'current_price': float(self.current_price),
            'unrealized_pnl': float(self.unrealized_pnl),
            'stop_loss': float(self.stop_loss) if self.stop_loss else None,
            'take_profit': float(self.take_profit) if self.take_profit else None,
            'status': self.status,
            'opened_at': self.opened_at.isoformat(),
            'closed_at': self.closed_at.isoformat() if self.closed_at else None
        }

class AIAnalysis(db.Model):
    """AI analysis results and decisions"""
    __tablename__ = 'ai_analysis'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    analysis_type = db.Column(db.String(50), nullable=False)  # market_analysis, signal_generation, risk_assessment
    input_data = db.Column(db.Text)  # JSON string of input data
    ai_response = db.Column(db.Text)  # JSON string of AI response
    confidence_score = db.Column(db.Numeric(5, 2))  # 0-100 confidence score
    recommendation = db.Column(db.String(20))  # BUY, SELL, HOLD
    model_used = db.Column(db.String(50), default='deepseek-chat')
    tokens_used = db.Column(db.Integer, default=0)
    cost = db.Column(db.Numeric(10, 6), default=0)
    processing_time = db.Column(db.Numeric(8, 3))  # seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    trades = db.relationship('Trade', backref='ai_analysis', lazy=True)
    
    def set_input_data(self, data):
        """Store input data as JSON"""
        self.input_data = json.dumps(data)
    
    def get_input_data(self):
        """Retrieve input data from JSON"""
        return json.loads(self.input_data) if self.input_data else {}
    
    def set_ai_response(self, response):
        """Store AI response as JSON"""
        self.ai_response = json.dumps(response)
    
    def get_ai_response(self):
        """Retrieve AI response from JSON"""
        return json.loads(self.ai_response) if self.ai_response else {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'analysis_type': self.analysis_type,
            'input_data': self.get_input_data(),
            'ai_response': self.get_ai_response(),
            'confidence_score': float(self.confidence_score) if self.confidence_score else None,
            'recommendation': self.recommendation,
            'model_used': self.model_used,
            'tokens_used': self.tokens_used,
            'cost': float(self.cost),
            'processing_time': float(self.processing_time) if self.processing_time else None,
            'created_at': self.created_at.isoformat()
        }

class MarketData(db.Model):
    """Historical and real-time market data"""
    __tablename__ = 'market_data'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    open_price = db.Column(db.Numeric(18, 8), nullable=False)
    high_price = db.Column(db.Numeric(18, 8), nullable=False)
    low_price = db.Column(db.Numeric(18, 8), nullable=False)
    close_price = db.Column(db.Numeric(18, 8), nullable=False)
    volume = db.Column(db.Numeric(18, 8), nullable=False)
    timeframe = db.Column(db.String(10), nullable=False)  # 1m, 5m, 1h, 1d
    
    # Technical indicators (calculated)
    sma_20 = db.Column(db.Numeric(18, 8))  # 20-period Simple Moving Average
    ema_12 = db.Column(db.Numeric(18, 8))  # 12-period Exponential Moving Average
    ema_26 = db.Column(db.Numeric(18, 8))  # 26-period Exponential Moving Average
    rsi_14 = db.Column(db.Numeric(5, 2))   # 14-period RSI
    macd = db.Column(db.Numeric(18, 8))    # MACD line
    macd_signal = db.Column(db.Numeric(18, 8))  # MACD signal line
    
    __table_args__ = (db.Index('idx_symbol_timeframe_timestamp', 'symbol', 'timeframe', 'timestamp'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'open_price': float(self.open_price),
            'high_price': float(self.high_price),
            'low_price': float(self.low_price),
            'close_price': float(self.close_price),
            'volume': float(self.volume),
            'timeframe': self.timeframe,
            'sma_20': float(self.sma_20) if self.sma_20 else None,
            'ema_12': float(self.ema_12) if self.ema_12 else None,
            'ema_26': float(self.ema_26) if self.ema_26 else None,
            'rsi_14': float(self.rsi_14) if self.rsi_14 else None,
            'macd': float(self.macd) if self.macd else None,
            'macd_signal': float(self.macd_signal) if self.macd_signal else None
        }

class RiskEvent(db.Model):
    """Risk management events and alerts"""
    __tablename__ = 'risk_events'
    
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # daily_loss_limit, position_size_exceeded, etc.
    severity = db.Column(db.String(20), nullable=False)  # low, medium, high, critical
    description = db.Column(db.Text, nullable=False)
    trade_id = db.Column(db.Integer, db.ForeignKey('trades.id'))
    position_id = db.Column(db.Integer, db.ForeignKey('positions.id'))
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'event_type': self.event_type,
            'severity': self.severity,
            'description': self.description,
            'trade_id': self.trade_id,
            'position_id': self.position_id,
            'resolved': self.resolved,
            'created_at': self.created_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }

class SystemConfig(db.Model):
    """System configuration and settings"""
    __tablename__ = 'system_config'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat()
        }

