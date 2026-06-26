import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BacktestValidator:
    """Validates backtest data and execution to prevent common biases."""

    @staticmethod
    def check_lookahead_bias(signals: List[Dict[str, Any]], data: List[Dict[str, Any]]) -> bool:
        """
        Checks if any trading signal uses data from the future.
        Returns True if lookahead bias is detected, False otherwise.
        """
        # A simple check: ensure signal generation timestamp is >= data timestamp
        # In a real system, this would be more complex, tracking the exact time data becomes available
        for signal in signals:
            signal_time = signal.get("timestamp")
            if not signal_time:
                continue
                
            for row in data:
                row_time = row.get("timestamp")
                if not row_time:
                    continue
                
                # If a signal generated at T uses data from T+1, that's lookahead bias
                if row_time > signal_time and signal.get("uses_data_from") == row_time:
                    logger.error(f"Lookahead bias detected! Signal at {signal_time} uses data from {row_time}")
                    return True
        return False

    @staticmethod
    def check_data_snooping(strategy_parameters: Dict[str, Any], runs: int) -> bool:
        """
        Warns if a strategy is over-optimized by checking the number of runs.
        """
        if runs > 100:
            logger.warning(f"High risk of data snooping: Strategy tested {runs} times.")
            return True
        return False
