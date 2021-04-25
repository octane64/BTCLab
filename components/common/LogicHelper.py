def is_better_than_previous(new_order, previous_order, min_discount) -> bool:
    discount = abs(new_order["Last price"] / previous_order["Last price"] - 1)
    return discount > min_discount