def is_better_than_previous(new_order, previous_order, min_discount) -> bool:
    assert min_discount > 0, 'min_discount should be a positive number'
    
    if previous_order is None:
        return True

    discount = new_order['price'] / previous_order['price'] - 1
    return discount < 0 and abs(discount) > min_discount/100