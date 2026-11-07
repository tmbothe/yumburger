"""Domain vocabulary for YumBurger synthetic data generation."""

MENU_CATEGORIES = ["Burger", "Chicken", "Fish", "Sides", "Beverages", "Desserts", "Breakfast", "Combo"]

MENU_ITEMS = [
    # Burgers
    {"name": "YumBurger Classic", "category": "Burger", "price_usd": 3.99, "calories": 490},
    {"name": "YumBurger Double", "category": "Burger", "price_usd": 5.49, "calories": 740},
    {"name": "YumBurger Deluxe", "category": "Burger", "price_usd": 6.49, "calories": 630},
    {"name": "Quarter Yum", "category": "Burger", "price_usd": 5.29, "calories": 520},
    {"name": "Quarter Yum with Cheese", "category": "Burger", "price_usd": 5.79, "calories": 570},
    {"name": "Big Yum", "category": "Burger", "price_usd": 5.99, "calories": 550},
    # Chicken
    {"name": "Crispy Chicken Sandwich", "category": "Chicken", "price_usd": 5.19, "calories": 470},
    {"name": "Spicy Chicken Deluxe", "category": "Chicken", "price_usd": 5.69, "calories": 530},
    {"name": "Chicken McNuggets 6pc", "category": "Chicken", "price_usd": 3.29, "calories": 250},
    {"name": "Chicken McNuggets 10pc", "category": "Chicken", "price_usd": 4.99, "calories": 420},
    {"name": "Chicken McNuggets 20pc", "category": "Chicken", "price_usd": 8.49, "calories": 840},
    # Fish
    {"name": "Filet-O-Yum", "category": "Fish", "price_usd": 4.49, "calories": 380},
    # Sides
    {"name": "Small Fries", "category": "Sides", "price_usd": 1.89, "calories": 230},
    {"name": "Medium Fries", "category": "Sides", "price_usd": 2.49, "calories": 320},
    {"name": "Large Fries", "category": "Sides", "price_usd": 2.99, "calories": 490},
    {"name": "Apple Slices", "category": "Sides", "price_usd": 1.29, "calories": 15},
    {"name": "Side Salad", "category": "Sides", "price_usd": 2.49, "calories": 20},
    # Beverages
    {"name": "Small Soft Drink", "category": "Beverages", "price_usd": 1.00, "calories": 150},
    {"name": "Medium Soft Drink", "category": "Beverages", "price_usd": 1.29, "calories": 210},
    {"name": "Large Soft Drink", "category": "Beverages", "price_usd": 1.49, "calories": 280},
    {"name": "Coffee Small", "category": "Beverages", "price_usd": 1.00, "calories": 0},
    {"name": "Coffee Large", "category": "Beverages", "price_usd": 1.69, "calories": 0},
    {"name": "Milkshake Chocolate", "category": "Beverages", "price_usd": 3.59, "calories": 530},
    {"name": "Orange Juice", "category": "Beverages", "price_usd": 1.99, "calories": 140},
    # Desserts
    {"name": "Soft Serve Cone", "category": "Desserts", "price_usd": 1.00, "calories": 200},
    {"name": "McFlurry Oreo", "category": "Desserts", "price_usd": 3.49, "calories": 510},
    {"name": "Apple Pie", "category": "Desserts", "price_usd": 1.49, "calories": 240},
    # Breakfast
    {"name": "Egg Yum Muffin", "category": "Breakfast", "price_usd": 3.99, "calories": 300},
    {"name": "Sausage McMuffin", "category": "Breakfast", "price_usd": 2.49, "calories": 400},
    {"name": "Hotcakes", "category": "Breakfast", "price_usd": 3.99, "calories": 580},
]

SUPPLIER_CATEGORIES = ["Beef", "Chicken", "Fish", "Produce", "Dairy", "Bread", "Beverages", "Packaging"]

SUPPLIER_NAMES = {
    "Beef": ["Keystone Foods", "OSI Group", "Golden State Foods", "Martin-Brower", "AmeriQwest Foods"],
    "Chicken": ["Tyson Foods", "Pilgrim's Pride", "Koch Foods", "Mountaire Farms"],
    "Fish": ["Trident Seafoods", "Pacific Seafood", "High Liner Foods"],
    "Produce": ["Fresh Del Monte", "Dole Food", "Naturipe Farms", "Taylor Farms"],
    "Dairy": ["Schreiber Foods", "Leprino Foods", "Prairie Farms"],
    "Bread": ["Bimbo Bakeries", "Flowers Foods", "Rotella's Italian Bakery"],
    "Beverages": ["Coca-Cola", "PepsiCo", "Dr Pepper", "Nestle Waters"],
    "Packaging": ["Pactiv Evergreen", "Novatek International", "Vegware"],
}

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West", "Northwest"]

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

REGION_STATES: dict[str, list[str]] = {
    "Northeast": ["ME", "NH", "VT", "MA", "RI", "CT", "NY", "NJ", "PA"],
    "Southeast": ["DE", "MD", "VA", "WV", "NC", "SC", "GA", "FL", "AL", "MS", "TN", "KY"],
    "Midwest": ["OH", "MI", "IN", "IL", "WI", "MN", "IA", "MO", "ND", "SD", "NE", "KS"],
    "Southwest": ["TX", "OK", "AR", "LA", "NM", "AZ"],
    "West": ["CA", "NV", "UT", "CO", "WY", "MT", "ID"],
    "Northwest": ["WA", "OR", "AK", "HI"],
}

CUSTOMER_TIERS = ["Bronze", "Silver", "Gold", "Platinum"]

PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Mobile Pay", "Gift Card"]

ORDER_CHANNELS = ["In-Store", "Drive-Through", "Mobile App", "Delivery"]
