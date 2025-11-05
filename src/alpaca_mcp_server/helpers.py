import re
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.models import Order
from alpaca.trading.requests import MarketOrderRequest, OptionLegRequest


def _validate_amount(amount: int, unit: TimeFrameUnit) -> bool:
    if amount <= 0:
        return False
    if unit == TimeFrameUnit.Minute and amount > 59:
        return False
    if unit == TimeFrameUnit.Hour and amount > 23:
        return False
    if unit in [TimeFrameUnit.Day, TimeFrameUnit.Week, TimeFrameUnit.Month] and amount > 365:
        return False
    return True

def parse_timeframe_with_enums(timeframe_str: str) -> Optional[TimeFrame]:
    try:
        if not timeframe_str or not isinstance(timeframe_str, str):
            return None
        timeframe_str = timeframe_str.strip()
        if not timeframe_str:
            return None

        predefined_timeframes = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
            "1Week": TimeFrame.Week,
            "1Month": TimeFrame.Month,
        }
        if timeframe_str in predefined_timeframes:
            return predefined_timeframes[timeframe_str]

        normalized = re.sub(r"\s+", " ", timeframe_str.lower().strip())
        direct_mappings = {
            "half hour": (30, TimeFrameUnit.Minute),
            "quarter hour": (15, TimeFrameUnit.Minute),
            "hourly": (1, TimeFrameUnit.Hour),
            "daily": (1, TimeFrameUnit.Day),
            "weekly": (1, TimeFrameUnit.Week),
            "monthly": (1, TimeFrameUnit.Month),
        }
        if normalized in direct_mappings:
            amount, unit = direct_mappings[normalized]
            return TimeFrame(amount, unit)

        pattern = r"^(\d+)\s*[-\s]*\s*(min|minute|minutes|hr|hour|hours|day|days|week|weeks|month|months)s?$"
        match = re.match(pattern, normalized)
        if match:
            amount = int(match.group(1))
            unit_str = match.group(2)
            unit_mapping = {
                "min": TimeFrameUnit.Minute,
                "minute": TimeFrameUnit.Minute,
                "minutes": TimeFrameUnit.Minute,
                "hr": TimeFrameUnit.Hour,
                "hour": TimeFrameUnit.Hour,
                "hours": TimeFrameUnit.Hour,
                "day": TimeFrameUnit.Day,
                "days": TimeFrameUnit.Day,
                "week": TimeFrameUnit.Week,
                "weeks": TimeFrameUnit.Week,
                "month": TimeFrameUnit.Month,
                "months": TimeFrameUnit.Month,
            }
            unit = unit_mapping.get(unit_str)
            if unit and _validate_amount(amount, unit):
                return TimeFrame(amount, unit)

        alpaca_pattern = r"^(\d+)(min|hour|day|week|month)s?$"
        match = re.match(alpaca_pattern, normalized)
        if match:
            amount = int(match.group(1))
            unit_str = match.group(2)
            unit_mapping = {
                "min": TimeFrameUnit.Minute,
                "hour": TimeFrameUnit.Hour,
                "day": TimeFrameUnit.Day,
                "week": TimeFrameUnit.Week,
                "month": TimeFrameUnit.Month,
            }
            unit = unit_mapping.get(unit_str)
            if unit and _validate_amount(amount, unit):
                return TimeFrame(amount, unit)

        return None
    except (ValueError, AttributeError, TypeError):
        return None

def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        s = s + "T00:00:00"
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception as e:
        raise ValueError(f"Invalid ISO datetime: {value}") from e


def _parse_date_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _month_name_to_number(name: str) -> int:
    try:
        return datetime.strptime(name.title(), "%B").month
    except ValueError:
        return datetime.strptime(name.title(), "%b").month


def _format_ohlcv_bar(bar, bar_type: str, include_time: bool = True) -> str:
    if not bar:
        return ""
    time_format = "%Y-%m-%d %H:%M:%S %Z" if include_time else "%Y-%m-%d"
    time_label = "Timestamp" if include_time else "Date"
    return f"""{bar_type}:
  Open: ${bar.open:.2f}, High: ${bar.high:.2f}, Low: ${bar.low:.2f}, Close: ${bar.close:.2f}
  Volume: {bar.volume:,}, {time_label}: {bar.timestamp.strftime(time_format)}
"""


def _format_quote_data(quote) -> str:
    if not quote:
        return ""
    return f"""Latest Quote:
  Bid: ${quote.bid_price:.2f} x {quote.bid_size}, Ask: ${quote.ask_price:.2f} x {quote.ask_size}
  Timestamp: {quote.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}
"""


def _format_trade_data(trade) -> str:
    if not trade:
        return ""
    optional_fields: List[str] = []
    if hasattr(trade, "exchange") and trade.exchange:
        optional_fields.append(f"Exchange: {trade.exchange}")
    if hasattr(trade, "conditions") and trade.conditions:
        optional_fields.append(f"Conditions: {trade.conditions}")
    if hasattr(trade, "id") and trade.id:
        optional_fields.append(f"ID: {trade.id}")
    optional_str = f", {', '.join(optional_fields)}" if optional_fields else ""
    return f"""Latest Trade:
            Price: ${trade.price:.2f}, Size: {trade.size}{optional_str}
            Timestamp: {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}
            """


def _parse_expiration_expression(expression: str) -> Dict[str, Any]:
    expression = expression.strip().lower()

    week_pattern = r"week\s+of\s+(\w+)\s+(\d{1,2}),?\s+(\d{4})"
    week_match = re.search(week_pattern, expression)
    if week_match:
        month_name, day_str, year_str = week_match.groups()
        try:
            month_num = _month_name_to_number(month_name)
            day = int(day_str)
            year = int(year_str)
            anchor_date = datetime(year, month_num, day).date()
            days_since_monday = anchor_date.weekday()
            week_start = anchor_date - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=4)
            return {
                "expiration_date_gte": week_start,
                "expiration_date_lte": week_end,
                "description": f"week of {month_name.title()} {day}, {year}",
            }
        except (ValueError, AttributeError) as e:
            return {"error": f"Invalid date in expression: {str(e)}"}

    month_pattern = r"month\s+of\s+(\w+)\s+(\d{4})"
    month_match = re.search(month_pattern, expression)
    if month_match:
        month_name, year_str = month_match.groups()
        try:
            month_num = _month_name_to_number(month_name)
            year = int(year_str)
            start_date = datetime(year, month_num, 1).date()
            end_date = (
                datetime(year + 1, 1, 1).date() - timedelta(days=1)
                if month_num == 12
                else datetime(year, month_num + 1, 1).date() - timedelta(days=1)
            )
            return {
                "expiration_date_gte": start_date,
                "expiration_date_lte": end_date,
                "description": f"month of {month_name.title()} {year}",
            }
        except (ValueError, AttributeError) as e:
            return {"error": f"Invalid month/year in expression: {str(e)}"}

    date_pattern = r"(\w+)\s+(\d{1,2}),?\s+(\d{4})"
    date_match = re.search(date_pattern, expression)
    if date_match:
        month_name, day_str, year_str = date_match.groups()
        try:
            month_num = _month_name_to_number(month_name)
            day = int(day_str)
            year = int(year_str)
            specific_date = datetime(year, month_num, day).date()
            return {
                "expiration_date": specific_date,
                "description": f"{month_name.title()} {day}, {year}",
            }
        except (ValueError, AttributeError) as e:
            return {"error": f"Invalid date in expression: {str(e)}"}

    return {
        "error": "Unable to parse expression '{expression}'. Supported formats: 'week of September 7, 2025', 'month of December 2025', 'September 7, 2025'",
    }


def _validate_option_order_inputs(legs: List[Dict[str, Any]], quantity: int, time_in_force: Union[str, TimeInForce]) -> Optional[str]:
    if not legs:
        return "Error: No option legs provided"
    if len(legs) > 4:
        return "Error: Maximum of 4 legs allowed for option orders"
    if quantity <= 0:
        return "Error: Quantity must be positive"
    if isinstance(time_in_force, str):
        if time_in_force.lower() != "day":
            return "Error: Only 'day' time_in_force is supported for options trading"
    elif isinstance(time_in_force, TimeInForce):
        if time_in_force != TimeInForce.DAY:
            return "Error: Only DAY time_in_force is supported for options trading"
    else:
        return f"Error: Invalid time_in_force type: {type(time_in_force)}. Must be string or TimeInForce enum."
    return None


def _convert_order_class_string(order_class: Optional[Union[str, OrderClass]]) -> Union[OrderClass, str]:
    if order_class is None:
        return order_class
    if isinstance(order_class, OrderClass):
        return order_class
    if isinstance(order_class, str):
        order_class_upper = order_class.upper()
        class_mapping = {
            "SIMPLE": OrderClass.SIMPLE,
            "BRACKET": OrderClass.BRACKET,
            "OCO": OrderClass.OCO,
            "OTO": OrderClass.OTO,
            "MLEG": OrderClass.MLEG,
        }
        if order_class_upper in class_mapping:
            return class_mapping[order_class_upper]
        else:
            return f"Invalid order class: {order_class}. Must be one of: simple, bracket, oco, oto, mleg"
    else:
        return f"Invalid order class type: {type(order_class)}. Must be string or OrderClass enum."


def _process_option_legs(legs: List[Dict[str, Any]]) -> Union[List[OptionLegRequest], str]:
    order_legs: List[OptionLegRequest] = []
    for leg in legs:
        if not isinstance(leg["ratio_qty"], int) or leg["ratio_qty"] <= 0:
            return f"Error: Invalid ratio_qty for leg {leg['symbol']}. Must be positive integer."
        if leg["side"].lower() == "buy":
            order_side = OrderSide.BUY
        elif leg["side"].lower() == "sell":
            order_side = OrderSide.SELL
        else:
            return f"Invalid order side: {leg['side']}. Must be 'buy' or 'sell'."
        order_legs.append(OptionLegRequest(symbol=leg["symbol"], side=order_side, ratio_qty=leg["ratio_qty"]))
    return order_legs


def _create_option_market_order_request(
    order_legs: List[OptionLegRequest],
    order_class: OrderClass,
    quantity: int,
    time_in_force: TimeInForce,
    extended_hours: bool,
) -> MarketOrderRequest:
    if order_class == OrderClass.MLEG:
        return MarketOrderRequest(
            qty=quantity,
            order_class=order_class,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            client_order_id=f"mcp_opt_{int(time.time())}",
            type=OrderType.MARKET,
            legs=order_legs,
        )
    else:
        return MarketOrderRequest(
            symbol=order_legs[0].symbol,
            qty=quantity,
            side=order_legs[0].side,
            order_class=order_class,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            client_order_id=f"mcp_opt_{int(time.time())}",
            type=OrderType.MARKET,
        )


def _format_option_order_response(order: Order, order_class: OrderClass, order_legs: List[OptionLegRequest]) -> str:
    result = f"""
            Option Market Order Placed Successfully:
            --------------------------------------
            Order ID: {order.id}
            Client Order ID: {order.client_order_id}
            Order Class: {order.order_class}
            Order Type: {order.type}
            Time In Force: {order.time_in_force}
            Status: {order.status}
            Quantity: {order.qty}
            Created At: {order.created_at}
            Updated At: {order.updated_at}
            """
    if order_class == OrderClass.MLEG and order.legs:
        result += "\nLegs:\n"
        for leg in order.legs:
            result += f"""
                    Symbol: {leg.symbol}
                    Side: {leg.side}
                    Ratio Quantity: {leg.ratio_qty}
                    Status: {leg.status}
                    Asset Class: {leg.asset_class}
                    Created At: {leg.created_at}
                    Updated At: {leg.updated_at}
                    Filled Price: {leg.filled_avg_price if hasattr(leg, 'filled_avg_price') else 'Not filled'}
                    Filled Time: {leg.filled_at if hasattr(leg, 'filled_at') else 'Not filled'}
                    -------------------------
                    """
    else:
        result += f"""
                Symbol: {order.symbol}
                Side: {order_legs[0].side}
                Filled Price: {order.filled_avg_price if hasattr(order, 'filled_avg_price') else 'Not filled'}
                Filled Time: {order.filled_at if hasattr(order, 'filled_at') else 'Not filled'}
                -------------------------
                """
    return result


def _analyze_option_strategy_type(order_legs: List[OptionLegRequest], order_class: OrderClass) -> Tuple[bool, bool, bool]:
    is_short_straddle = False
    is_short_strangle = False
    is_short_calendar = False
    if order_class == OrderClass.MLEG and len(order_legs) == 2:
        both_short = order_legs[0].side == OrderSide.SELL and order_legs[1].side == OrderSide.SELL
        if both_short:
            if order_legs[0].symbol.split("C")[0] == order_legs[1].symbol.split("P")[0]:
                is_short_straddle = True
            else:
                is_short_strangle = True
            leg1_type = "C" if "C" in order_legs[0].symbol else "P"
            leg2_type = "C" if "C" in order_legs[1].symbol else "P"
            if leg1_type == "C" and leg2_type == "C":
                leg1_exp = order_legs[0].symbol.split(leg1_type)[1][:6]
                leg2_exp = order_legs[1].symbol.split(leg2_type)[1][:6]
                if leg1_exp != leg2_exp:
                    is_short_calendar = True
                    is_short_strangle = False
    return is_short_straddle, is_short_strangle, is_short_calendar


def _get_short_straddle_error_message() -> str:
    return """
    Error: Account not eligible to trade short straddles.
    
    This error occurs because short straddles require Level 4 options trading permission.
    A short straddle involves:
    - Selling a call option
    - Selling a put option
    - Both options have the same strike price and expiration
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long straddle instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """


def _get_short_strangle_error_message() -> str:
    return """
    Error: Account not eligible to trade short strangles.
    
    This error occurs because short strangles require Level 4 options trading permission.
    A short strangle involves:
    - Selling an out-of-the-money call option
    - Selling an out-of-the-money put option
    - Both options have the same expiration
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long strangle instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """


def _get_short_calendar_error_message() -> str:
    return """
    Error: Account not eligible to trade short calendar spreads.
    
    This error occurs because short calendar spreads require Level 4 options trading permission.
    A short calendar spread involves:
    - Selling a longer-term option
    - Selling a shorter-term option
    - Both options have the same strike price
    
    Required Account Level:
    - Level 4 options trading permission is required
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using a long calendar spread instead
    - Use a debit spread strategy
    - Implement a covered call or cash-secured put
    """


def _get_uncovered_options_error_message() -> str:
    return """
    Error: Account not eligible to trade uncovered option contracts.
    
    This error occurs when attempting to place an order that could result in an uncovered position.
    Common scenarios include:
    1. Selling naked calls
    2. Calendar spreads where the short leg expires after the long leg
    3. Other strategies that could leave uncovered positions
    
    Required Account Level:
    - Level 4 options trading permission is required for uncovered options
    - Please contact your broker to upgrade your account level if needed
    
    Alternative Strategies:
    - Consider using covered calls instead of naked calls
    - Use debit spreads instead of calendar spreads
    - Ensure all positions are properly hedged
    """


def _handle_option_api_error(error_message: str, order_legs: List[OptionLegRequest], order_class: OrderClass) -> str:
    if "40310000" in error_message and "not eligible to trade uncovered option contracts" in error_message:
        is_short_straddle, is_short_strangle, is_short_calendar = _analyze_option_strategy_type(order_legs, order_class)
        if is_short_straddle:
            return _get_short_straddle_error_message()
        elif is_short_strangle:
            return _get_short_strangle_error_message()
        elif is_short_calendar:
            return _get_short_calendar_error_message()
        else:
            return _get_uncovered_options_error_message()
    elif "403" in error_message:
        return f"""
        Error: Permission denied for option trading.
        
        Possible reasons:
        1. Insufficient account level for the requested strategy
        2. Account restrictions on option trading
        3. Missing required permissions
        
        Please check:
        1. Your account's option trading level
        2. Any specific restrictions on your account
        3. Required permissions for the strategy you're trying to implement
        
        Original error: {error_message}
        """
    else:
        return f"""
        Error placing option order: {error_message}
        
        Please check:
        1. All option symbols are valid
        2. Your account has sufficient buying power
        3. The market is open for trading
        4. Your account has the required permissions
        """


