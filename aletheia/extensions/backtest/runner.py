import uuid
import logging
from typing import List, Dict, Any
from aletheia.extensions.backtest.models import BacktestResult, Order, Position
from aletheia.extensions.backtest.metrics import (
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor
)
from aletheia.extensions.backtest.validation import BacktestValidator

logger = logging.getLogger(__name__)

class BacktestRunner:
    """Event-driven backtest execution engine."""

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.orders: List[Order] = []
        self.positions: Dict[str, Position] = {}
        self.equity_curve: List[float] = [initial_capital]
        self.trades_pnl: List[float] = []
        self.daily_returns: List[float] = []

    def submit_order(self, symbol: str, order_type: str, action: str, quantity: float, price: float = None):
        order = Order(
            id=str(uuid.uuid4())[:8],
            symbol=symbol,
            order_type=order_type,
            action=action,
            quantity=quantity,
            price=price
        )
        self.orders.append(order)
        logger.info(f"Order submitted: {action} {quantity} {symbol}")
        return order

    def execute_orders(self, current_data: Dict[str, Any]):
        """Simulates order execution against current market data."""
        # Highly simplified execution model
        for order in self.orders:
            if order.status == "pending":
                # Assume market orders fill immediately at current price
                current_price = current_data.get(order.symbol, {}).get("close")
                if current_price is None:
                    continue
                
                order.filled_price = current_price
                order.status = "filled"
                
                if order.action == "buy":
                    cost = order.quantity * current_price
                    if self.current_capital >= cost:
                        self.current_capital -= cost
                        if order.symbol in self.positions:
                            pos = self.positions[order.symbol]
                            total_cost = (pos.quantity * pos.average_entry_price) + cost
                            pos.quantity += order.quantity
                            pos.average_entry_price = total_cost / pos.quantity
                        else:
                            self.positions[order.symbol] = Position(
                                symbol=order.symbol,
                                quantity=order.quantity,
                                average_entry_price=current_price,
                                current_price=current_price
                            )
                elif order.action == "sell":
                    if order.symbol in self.positions and self.positions[order.symbol].quantity >= order.quantity:
                        pos = self.positions[order.symbol]
                        revenue = order.quantity * current_price
                        self.current_capital += revenue
                        
                        # Calculate PnL for this trade
                        pnl = (current_price - pos.average_entry_price) * order.quantity
                        self.trades_pnl.append(pnl)
                        
                        pos.quantity -= order.quantity
                        if pos.quantity == 0:
                            del self.positions[order.symbol]

    def update_equity(self, current_data: Dict[str, Any]):
        """Updates portfolio value based on current prices."""
        total_value = self.current_capital
        for symbol, pos in self.positions.items():
            current_price = current_data.get(symbol, {}).get("close", pos.current_price)
            pos.current_price = current_price
            pos.unrealized_pnl = (current_price - pos.average_entry_price) * pos.quantity
            total_value += pos.quantity * current_price
        
        # Calculate daily return
        prev_value = self.equity_curve[-1]
        daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0
        self.daily_returns.append(daily_return)
        
        self.equity_curve.append(total_value)

    def generate_report(self, strategy_name: str, start_date: str, end_date: str) -> BacktestResult:
        total_return = (self.equity_curve[-1] - self.initial_capital) / self.initial_capital
        
        metrics = {
            "sharpe_ratio": calculate_sharpe_ratio(self.daily_returns),
            "max_drawdown": calculate_max_drawdown(self.equity_curve),
            "win_rate": calculate_win_rate(self.trades_pnl),
            "profit_factor": calculate_profit_factor(self.trades_pnl),
            "total_trades": len(self.trades_pnl)
        }
        
        equity_data = [{"step": i, "value": val} for i, val in enumerate(self.equity_curve)]
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_capital=self.equity_curve[-1],
            total_return=total_return,
            metrics=metrics,
            orders=self.orders,
            equity_curve=equity_data
        )
