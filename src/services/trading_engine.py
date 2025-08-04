"""
Trading Engine - Core business logic for the cryptocurrency trading bot
Handles AI integration, risk management, and trade execution
"""

import os
import time
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import requests
from openai import OpenAI

from src.models.trading import db, Account, Trade, Position, AIAnalysis, MarketData, RiskEvent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingEngine:
    """Main trading engine that coordinates AI analysis, risk management, and trade execution"""
    
    def __init__(self):
        self.deepseek_client = self._initialize_deepseek()
        self.exchange_apis = {}
        self.risk_manager = RiskManager()
        self.market_analyzer = MarketAnalyzer()
        
    def _initialize_deepseek(self):
        """Initialize DeepSeek AI client"""
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            logger.warning("DEEPSEEK_API_KEY not found in environment variables")
            return None
            
        return OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
    
    def analyze_market_and_generate_signal(self, account_id: int, symbol: str) -> Optional[Dict]:
        """
        Main trading pipeline: analyze market conditions and generate trading signals
        """
        try:
            # Get account information
            account = Account.query.get(account_id)
            if not account or account.status != 'active':
                logger.warning(f"Account {account_id} not active or not found")
                return None
            
            # Get market data
            market_data = self.market_analyzer.get_market_data(symbol)
            if not market_data:
                logger.error(f"Failed to get market data for {symbol}")
                return None
            
            # Calculate technical indicators
            technical_analysis = self.market_analyzer.calculate_technical_indicators(market_data)
            
            # Check risk constraints
            risk_check = self.risk_manager.validate_new_trade(account, symbol)
            if not risk_check['allowed']:
                logger.warning(f"Risk check failed: {risk_check['reason']}")
                return None
            
            # Generate AI analysis
            ai_analysis = self._generate_ai_analysis(symbol, market_data, technical_analysis, account)
            if not ai_analysis:
                logger.error("Failed to generate AI analysis")
                return None
            
            # Create trading signal if AI recommends action
            if ai_analysis['recommendation'] in ['BUY', 'SELL']:
                signal = self._create_trading_signal(account, symbol, ai_analysis, market_data)
                return signal
            
            return {'action': 'HOLD', 'reason': 'AI recommends holding position'}
            
        except Exception as e:
            logger.error(f"Error in analyze_market_and_generate_signal: {str(e)}")
            return None
    
    def _generate_ai_analysis(self, symbol: str, market_data: Dict, technical_analysis: Dict, account: Account) -> Optional[Dict]:
        """Generate AI analysis using DeepSeek API"""
        if not self.deepseek_client:
            logger.error("DeepSeek client not initialized")
            return None
        
        try:
            # Prepare input data for AI
            input_data = {
                'symbol': symbol,
                'current_price': market_data['current_price'],
                'price_change_24h': market_data.get('price_change_24h', 0),
                'volume_24h': market_data.get('volume_24h', 0),
                'technical_indicators': technical_analysis,
                'account_balance': float(account.balance),
                'risk_percentage': float(account.risk_percentage),
                'open_positions': len(account.positions)
            }
            
            # Create system prompt
            system_prompt = self._create_system_prompt(account)
            
            # Create user prompt with market data
            user_prompt = self._create_analysis_prompt(input_data)
            
            # Call DeepSeek API
            start_time = time.time()
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                functions=[self._get_trading_functions()],
                function_call="auto",
                temperature=0.1,
                max_tokens=1000
            )
            
            processing_time = time.time() - start_time
            
            # Parse AI response
            ai_response = self._parse_ai_response(response)
            
            # Save AI analysis to database
            analysis = AIAnalysis(
                symbol=symbol,
                analysis_type='market_analysis',
                confidence_score=ai_response.get('confidence', 0),
                recommendation=ai_response.get('recommendation', 'HOLD'),
                model_used='deepseek-chat',
                tokens_used=response.usage.total_tokens,
                cost=self._calculate_api_cost(response.usage.total_tokens, 'deepseek-chat'),
                processing_time=processing_time
            )
            analysis.set_input_data(input_data)
            analysis.set_ai_response(ai_response)
            
            db.session.add(analysis)
            db.session.commit()
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error generating AI analysis: {str(e)}")
            return None
    
    def _create_system_prompt(self, account: Account) -> str:
        """Create system prompt for AI analysis"""
        return f"""You are an expert cryptocurrency trading assistant managing a ${account.balance} account with strict risk management rules.

ACCOUNT CONSTRAINTS:
- Current Balance: ${account.balance}
- Risk per Trade: {account.risk_percentage}% (${float(account.balance) * float(account.risk_percentage) / 100:.2f} max loss)
- Max Open Positions: {account.max_positions}
- Exchange: {account.exchange}

TRADING RULES:
1. NEVER risk more than {account.risk_percentage}% per trade
2. ALWAYS use stop-losses (2-3% below entry for long positions)
3. Focus on major cryptocurrencies (BTC, ETH, BNB) for better liquidity
4. Consider transaction fees (0.1% on Binance) in all calculations
5. Prioritize capital preservation over aggressive profits
6. Only trade when high-confidence signals are present

ANALYSIS FRAMEWORK:
1. Technical Analysis: Price action, volume, momentum indicators
2. Market Context: Overall market sentiment and trends
3. Risk Assessment: Position sizing and stop-loss placement
4. Trade Management: Entry timing and exit strategy

Respond with structured analysis including confidence score (0-100), recommendation (BUY/SELL/HOLD), entry price, stop-loss, take-profit, and detailed reasoning."""
    
    def _create_analysis_prompt(self, input_data: Dict) -> str:
        """Create analysis prompt with market data"""
        return f"""Analyze the following market data for {input_data['symbol']} and provide trading recommendation:

CURRENT MARKET DATA:
- Price: ${input_data['current_price']}
- 24h Change: {input_data['price_change_24h']:.2f}%
- 24h Volume: ${input_data['volume_24h']:,.0f}
- Open Positions: {input_data['open_positions']}

TECHNICAL INDICATORS:
{json.dumps(input_data['technical_indicators'], indent=2)}

ACCOUNT STATUS:
- Available Balance: ${input_data['account_balance']}
- Risk per Trade: {input_data['risk_percentage']}%
- Max Risk Amount: ${input_data['account_balance'] * input_data['risk_percentage'] / 100:.2f}

Please analyze this data and provide:
1. Market sentiment assessment
2. Technical analysis summary
3. Trading recommendation (BUY/SELL/HOLD)
4. Confidence score (0-100)
5. If recommending BUY/SELL: entry price, stop-loss, take-profit levels
6. Position size recommendation
7. Risk assessment and reasoning

Format your response as JSON with the following structure:
{{
    "recommendation": "BUY|SELL|HOLD",
    "confidence": 85,
    "entry_price": 45000.00,
    "stop_loss": 43650.00,
    "take_profit": 47250.00,
    "position_size": 0.001,
    "risk_reward_ratio": 2.5,
    "reasoning": "Detailed explanation of the analysis and decision",
    "market_sentiment": "bullish|bearish|neutral",
    "technical_summary": "Summary of technical indicators"
}}"""
    
    def _get_trading_functions(self) -> Dict:
        """Define function calling schema for AI"""
        return {
            "name": "generate_trading_signal",
            "description": "Generate a trading signal based on market analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "recommendation": {
                        "type": "string",
                        "enum": ["BUY", "SELL", "HOLD"],
                        "description": "Trading recommendation"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Confidence score for the recommendation"
                    },
                    "entry_price": {
                        "type": "number",
                        "description": "Recommended entry price"
                    },
                    "stop_loss": {
                        "type": "number",
                        "description": "Stop loss price"
                    },
                    "take_profit": {
                        "type": "number",
                        "description": "Take profit price"
                    },
                    "position_size": {
                        "type": "number",
                        "description": "Recommended position size"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Detailed reasoning for the recommendation"
                    }
                },
                "required": ["recommendation", "confidence", "reasoning"]
            }
        }
    
    def _parse_ai_response(self, response) -> Dict:
        """Parse AI response and extract trading signal"""
        try:
            if response.choices[0].function_call:
                # Function calling response
                function_args = json.loads(response.choices[0].function_call.arguments)
                return function_args
            else:
                # Regular text response - try to parse JSON
                content = response.choices[0].message.content
                # Look for JSON in the response
                start = content.find('{')
                end = content.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = content[start:end]
                    return json.loads(json_str)
                else:
                    # Fallback parsing
                    return {
                        'recommendation': 'HOLD',
                        'confidence': 50,
                        'reasoning': content
                    }
        except Exception as e:
            logger.error(f"Error parsing AI response: {str(e)}")
            return {
                'recommendation': 'HOLD',
                'confidence': 0,
                'reasoning': 'Failed to parse AI response'
            }
    
    def _calculate_api_cost(self, total_tokens: int, model: str) -> float:
        """Calculate API cost based on token usage"""
        # DeepSeek pricing (per 1M tokens)
        if model == 'deepseek-chat':
            # Assuming mixed input/output tokens
            cost_per_1m = 0.55  # Average of input and output costs
        else:
            cost_per_1m = 1.0  # Default fallback
        
        return (total_tokens / 1_000_000) * cost_per_1m
    
    def _create_trading_signal(self, account: Account, symbol: str, ai_analysis: Dict, market_data: Dict) -> Dict:
        """Create a trading signal based on AI analysis"""
        try:
            recommendation = ai_analysis.get('recommendation', 'HOLD')
            confidence = ai_analysis.get('confidence', 0)
            
            if confidence < 70:  # Minimum confidence threshold
                return {
                    'action': 'HOLD',
                    'reason': f'Confidence too low: {confidence}%'
                }
            
            # Calculate position size based on risk management
            entry_price = ai_analysis.get('entry_price', market_data['current_price'])
            stop_loss = ai_analysis.get('stop_loss')
            
            if not stop_loss:
                # Calculate default stop loss (2% below entry for long)
                if recommendation == 'BUY':
                    stop_loss = entry_price * 0.98
                else:  # SELL
                    stop_loss = entry_price * 1.02
            
            # Calculate position size
            risk_amount = float(account.balance) * float(account.risk_percentage) / 100
            price_risk = abs(entry_price - stop_loss)
            position_size = risk_amount / price_risk
            
            # Validate position size doesn't exceed account balance
            position_value = position_size * entry_price
            if position_value > float(account.balance) * 0.95:  # Leave 5% buffer
                position_size = (float(account.balance) * 0.95) / entry_price
            
            return {
                'action': recommendation,
                'symbol': symbol,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': ai_analysis.get('take_profit'),
                'position_size': position_size,
                'confidence': confidence,
                'reasoning': ai_analysis.get('reasoning', ''),
                'ai_analysis_id': None  # Will be set when analysis is saved
            }
            
        except Exception as e:
            logger.error(f"Error creating trading signal: {str(e)}")
            return {
                'action': 'HOLD',
                'reason': f'Error creating signal: {str(e)}'
            }

class RiskManager:
    """Risk management system to validate trades and monitor positions"""
    
    def validate_new_trade(self, account: Account, symbol: str) -> Dict:
        """Validate if a new trade is allowed based on risk rules"""
        try:
            # Check if account is active
            if account.status != 'active':
                return {'allowed': False, 'reason': 'Account not active'}
            
            # Check maximum positions limit
            open_positions = Position.query.filter_by(
                account_id=account.id,
                status='open'
            ).count()
            
            if open_positions >= account.max_positions:
                return {'allowed': False, 'reason': f'Maximum positions limit reached ({account.max_positions})'}
            
            # Check daily loss limit (5% of account)
            today = datetime.utcnow().date()
            daily_trades = Trade.query.filter(
                Trade.account_id == account.id,
                Trade.created_at >= today,
                Trade.status == 'filled'
            ).all()
            
            daily_pnl = sum(self._calculate_trade_pnl(trade) for trade in daily_trades)
            daily_loss_limit = float(account.balance) * 0.05  # 5% daily loss limit
            
            if daily_pnl < -daily_loss_limit:
                return {'allowed': False, 'reason': f'Daily loss limit exceeded: ${abs(daily_pnl):.2f}'}
            
            # Check if already have position in this symbol
            existing_position = Position.query.filter_by(
                account_id=account.id,
                symbol=symbol,
                status='open'
            ).first()
            
            if existing_position:
                return {'allowed': False, 'reason': f'Already have open position in {symbol}'}
            
            return {'allowed': True, 'reason': 'Trade validation passed'}
            
        except Exception as e:
            logger.error(f"Error in risk validation: {str(e)}")
            return {'allowed': False, 'reason': f'Risk validation error: {str(e)}'}
    
    def _calculate_trade_pnl(self, trade: Trade) -> float:
        """Calculate P&L for a completed trade"""
        # This is a simplified calculation - in reality, you'd need to match buy/sell pairs
        return 0  # Placeholder

class MarketAnalyzer:
    """Market data analysis and technical indicators"""
    
    def get_market_data(self, symbol: str) -> Optional[Dict]:
        """Get current market data for a symbol"""
        try:
            # This would typically call exchange API
            # For now, return mock data
            return {
                'symbol': symbol,
                'current_price': 45000.0,
                'price_change_24h': 2.5,
                'volume_24h': 1000000000,
                'high_24h': 46000.0,
                'low_24h': 44000.0
            }
        except Exception as e:
            logger.error(f"Error getting market data: {str(e)}")
            return None
    
    def calculate_technical_indicators(self, market_data: Dict) -> Dict:
        """Calculate technical indicators"""
        # This would typically calculate real indicators
        # For now, return mock indicators
        return {
            'rsi_14': 65.5,
            'macd': 150.2,
            'macd_signal': 145.8,
            'sma_20': 44500.0,
            'ema_12': 44800.0,
            'ema_26': 44200.0,
            'bollinger_upper': 46000.0,
            'bollinger_lower': 43000.0,
            'volume_sma': 800000000
        }

