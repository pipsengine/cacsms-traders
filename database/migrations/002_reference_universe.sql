CREATE TABLE IF NOT EXISTS reference_currencies(code TEXT PRIMARY KEY,name TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN('FIAT','METAL','CRYPTO')));
CREATE TABLE IF NOT EXISTS reference_instruments(symbol TEXT PRIMARY KEY,base_code TEXT NOT NULL,quote_code TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
INSERT OR IGNORE INTO reference_currencies(code,name,kind) VALUES
('AUD','Australian Dollar','FIAT'),('CAD','Canadian Dollar','FIAT'),('CHF','Swiss Franc','FIAT'),('EUR','Euro','FIAT'),('GBP','Pound Sterling','FIAT'),('JPY','Japanese Yen','FIAT'),('NZD','New Zealand Dollar','FIAT'),('USD','US Dollar','FIAT'),('XAU','Gold','METAL'),('NGN','Nigerian Naira','FIAT');
INSERT OR IGNORE INTO reference_instruments(symbol,base_code,quote_code,enabled) VALUES
('AUDCAD','AUD','CAD',1),('AUDCHF','AUD','CHF',1),('AUDJPY','AUD','JPY',1),('AUDNZD','AUD','NZD',1),('AUDUSD','AUD','USD',1),
('CADCHF','CAD','CHF',1),('CADJPY','CAD','JPY',1),('CHFJPY','CHF','JPY',1),('EURAUD','EUR','AUD',1),('EURCAD','EUR','CAD',1),
('EURCHF','EUR','CHF',1),('EURGBP','EUR','GBP',1),('EURJPY','EUR','JPY',1),('EURNZD','EUR','NZD',1),('EURUSD','EUR','USD',1),
('GBPAUD','GBP','AUD',1),('GBPCAD','GBP','CAD',1),('GBPCHF','GBP','CHF',1),('GBPJPY','GBP','JPY',1),('GBPNZD','GBP','NZD',1),
('GBPUSD','GBP','USD',1),('NZDCAD','NZD','CAD',1),('NZDCHF','NZD','CHF',1),('NZDJPY','NZD','JPY',1),('NZDUSD','NZD','USD',1),
('USDCAD','USD','CAD',1),('USDCHF','USD','CHF',1),('USDJPY','USD','JPY',1),('XAUUSD','XAU','USD',1);
