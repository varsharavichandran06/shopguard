-- ShopGuard store schema. Money is integer cents. Dates are YYYY-MM-DD text.
CREATE TABLE store_config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE users (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  email   TEXT NOT NULL UNIQUE,
  zip     TEXT NOT NULL,
  address TEXT NOT NULL
);

CREATE TABLE products (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  category   TEXT NOT NULL,
  final_sale INTEGER NOT NULL DEFAULT 0 CHECK (final_sale IN (0, 1))
);

CREATE TABLE variants (
  id          TEXT PRIMARY KEY,
  product_id  TEXT NOT NULL REFERENCES products(id),
  size        TEXT NOT NULL,
  color       TEXT NOT NULL,
  price_cents INTEGER NOT NULL CHECK (price_cents > 0),
  stock       INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE orders (
  id               TEXT PRIMARY KEY,
  user_id          TEXT NOT NULL REFERENCES users(id),
  status           TEXT NOT NULL CHECK (status IN ('pending','processing','shipped','delivered','cancelled')),
  payment_method   TEXT NOT NULL CHECK (payment_method IN ('card','paypal','gift_card')),
  placed_at        TEXT NOT NULL,
  delivered_at     TEXT,
  shipping_address TEXT NOT NULL
);

CREATE TABLE order_items (
  id          TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL REFERENCES orders(id),
  variant_id  TEXT NOT NULL REFERENCES variants(id),
  price_cents INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','returned','exchanged'))
);

CREATE TABLE returns (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id      TEXT NOT NULL REFERENCES orders(id),
  item_id       TEXT NOT NULL REFERENCES order_items(id),
  refund_method TEXT NOT NULL CHECK (refund_method IN ('original_payment','store_credit')),
  amount_cents  INTEGER NOT NULL
);

CREATE TABLE exchanges (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id       TEXT NOT NULL REFERENCES orders(id),
  item_id        TEXT NOT NULL REFERENCES order_items(id),
  old_variant_id TEXT NOT NULL REFERENCES variants(id),
  new_variant_id TEXT NOT NULL REFERENCES variants(id)
);

CREATE TABLE order_events (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id),
  event    TEXT NOT NULL,
  detail   TEXT
);
