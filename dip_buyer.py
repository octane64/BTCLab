import time
import ccxt
from ccxt.base.errors import InsufficientFunds, BadSymbol
import components.common.APIHelper as APIHelper
import components.common.LogicHelper as LogicHelper
import components.common.Constants as Constants
import components.common.FileHelper as FileHelper


def main():
    config = FileHelper.get_config()

    bot_dummy_mode = config[Constants.CONFIG_BOT_KEY][Constants.CONFIG_DUMMY_MODE_KEY]
    bot_frequency = config[Constants.CONFIG_BOT_KEY][Constants.CONFIG_FREQUENCY_KEY]
    bot_insufficient_funds_wait_minutes = config[Constants.CONFIG_BOT_KEY][
        Constants.CONFIG_INSUFFICIENT_FUNDS_WAIT_MINUTES_KEY
    ]
    bot_min_initial_drop = config[Constants.CONFIG_BOT_KEY][
        Constants.CONFIG_MIN_INITIAL_DROP_KEY
    ]
    bot_min_additional_drop = config[Constants.CONFIG_BOT_KEY][
        Constants.CONFIG_MIN_ADDITIONAL_DROP_KEY
    ]
    bot_tickers = config[Constants.CONFIG_BOT_KEY][Constants.CONFIG_TICKERS_KEY]
    binance_public_key = config[Constants.CONFIG_BINANCE_KEY][
        Constants.CONFIG_PUBLIC_KEY
    ]
    binance_secret_key = config[Constants.CONFIG_BINANCE_KEY][
        Constants.CONFIG_SECRET_KEY
    ]
    telegram_bot_token = config[Constants.CONFIG_TELEGRAM_KEY][
        Constants.CONFIG_BOT_TOKEN_KEY
    ]
    telegram_chat_id = config[Constants.CONFIG_TELEGRAM_KEY][
        Constants.CONFIG_CHAT_ID_KEY
    ]

    print("Started monitoring crypto prices to buy significant dips")
    print("Symbols:", ", ".join(bot_tickers))
    print(f"Any drop of {bot_min_initial_drop}% or more will be bought")
    print(
        f"Subsecuent drops of more than {bot_min_additional_drop}% relative to previous buys in the same symbol will also be bought"
    )

    binance = ccxt.binance(
        {
            "apiKey": binance_public_key,
            "secret": binance_secret_key,
            "enableRateLimit": True,
        }
    )
    orders = {}

    while True:
        # What symbol has the biggest drop in the last 24 hours?
        biggest_drop = APIHelper.get_biggest_drop(binance, bot_tickers)

        if biggest_drop is None:
            print(
                f"None of the pairs has dropped in the last 24 hours. Checking again in {bot_frequency} minutes..."
            )
            time.sleep(bot_frequency * 60)
            continue
        else:
            print(
                f'{biggest_drop["Ticker"]} is down {biggest_drop["Pct change"]}% from the last 24 hours'
            )

        if biggest_drop["Pct change"] < -bot_min_initial_drop:
            previous_order = orders.get(biggest_drop["Ticker"])
            if previous_order is None or LogicHelper.is_better_than_previous(
                biggest_drop, previous_order, bot_min_additional_drop / 100
            ):
                try:
                    order = APIHelper.place_order(binance, biggest_drop, bot_dummy_mode)
                    # TODO Notify order placed to chat
                    print(order)
                except InsufficientFunds:
                    print(
                        f"Insufficient funds. Trying again in {bot_insufficient_funds_wait_minutes} minutes..."
                    )
                    time.sleep(bot_insufficient_funds_wait_minutes * 60)
                    continue
                    # TODO Notify fail to place order because insufficient funds to chat
                else:
                    orders[biggest_drop["Ticker"]] = biggest_drop
                    save(orders)

        time.sleep(bot_frequency * 60)


if __name__ == "__main__":
    main()
