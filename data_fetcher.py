from urllib.request import urlopen
import abc
import time
import datetime
import json
import psycopg2
from threading import Thread
from functools import partial

class StockFetcher(metaclass=abc.ABCMeta):
	"""
	Base class for fetching stock information
	"""
	def __init__(self, stocks):
	    self.stocks = stocks

	@abc.abstractmethod
	def fetchPrice(self, stock):
		"""
		returns current price of stock
		"""
		return NotImplemented

	@abc.abstractmethod
	def fetchStockHighLow(self, stock):
		"""
		returns the high/low values of stock
		"""
		return NotImplemented

	@abc.abstractmethod
	def fetchImageURL(self, stock):
		"""
		returns a URL pointing to the logo corresponding to stock
		"""
		return NotImplemented

class IEXStockFetcher(StockFetcher):
	"""
	Fetches stock information using iextrading.com API
	"""

	url_prefix = "https://api.iextrading.com/1.0/stock/"
	url_suffix_price = "/price"
	url_suffix_img = "/logo"
	url_suffix_highlow = "/quote"

	def __init__(self, stocks):
		super().__init__(stocks)

	def fetchAllPrices(self):
		stock_data = {}
		prices = {}
		stock_data['timestamp'] = datetime.datetime.now()
		threads = []
		for stock in self.stocks:
			t = Thread(target=partial(self.fetchPriceInto, stock, prices))
			threads.append(t)
			t.start()
		for t in threads:
			t.join()
		stock_data['prices'] = prices
		return stock_data

	def fetchAllImages(self):
		urls = {}
		threads = []
		for stock in self.stocks:
			t = Thread(target=partial(self.fetchURLInto, stock, urls))
			threads.append(t)
			t.start()
		for t in threads:
			t.join()
		return urls

	def fetchAllHighLow(self):
		high_low = {}
		threads = []
		for stock in self.stocks:
			t = Thread(target=partial(self.fetchHighLowInto, stock, high_low))
			threads.append(t)
			t.start()
		for t in threads:
			t.join()
		return high_low

	def fetchPriceInto(self, stock, results=None):
		results[stock] = self.fetchPrice(stock)

	def fetchURLInto(self, stock, results=None):
		results[stock] = self.fetchImageURL(stock)

	def fetchHighLowInto(self, stock, results=None):
		results[stock] = self.fetchStockHighLow(stock)

	def fetchPrice(self, stock):
		# get the price of a single stock
		try:
			resp = urlopen("{}{}{}".format(IEXStockFetcher.url_prefix, stock, IEXStockFetcher.url_suffix_price))
			price = float(resp.readlines()[0])
			return price
		except:
			return self.fetchPrice(stock)

	def fetchImageURL(self, stock):
		# get the image url of a single stock
		try:
			resp = urlopen("{}{}{}".format(IEXStockFetcher.url_prefix, stock, IEXStockFetcher.url_suffix_img))
			resp = json.loads(resp.readlines()[0].decode('utf8'))
			return resp['url']
		except:
			return self.fetchImageURL(stock)

	def fetchStockHighLow(self, stock):
		# get the image url of a single stock
		try:
			resp = urlopen("{}{}{}".format(IEXStockFetcher.url_prefix, stock, IEXStockFetcher.url_suffix_highlow))
			resp = json.loads(resp.readlines()[0].decode('utf8'))
			return (resp['week52High'], resp['week52Low'])
		except:
			return self.fetchStockHighLow(stock)

class PostgreSQLStockManager():
	"""
	Records fetched stock data in a postgreSQL table 
	"""

	def __init__(self, conn, stock_fetcher):
		self.conn = conn
		self.stock_fetcher = stock_fetcher

	def insertStock(self, table, timestamp, stock, price):
		"""
		records a timestamped stock value
		"""
		cur = self.conn.cursor()
		query = """
		INSERT INTO {} (time, stock_name, price) VALUES(
		\'{}\',
		\'{}\',
		{});
		""".format(table, timestamp, stock, price)
		cur.execute(query)
		self.conn.commit()

	def updateStockURL(self, table, stock, url):
		"""
		updates the table containing stock logo URLs
		"""
		cur = self.conn.cursor()
		delete_query = """
		DELETE FROM {}
		WHERE stock_name=\'{}\';
		""".format(table, stock)
		query = """
		INSERT INTO {} (stock_name, image_url) VALUES(
		\'{}\',
		\'{}\');
		""".format(table, stock, url)
		cur.execute(delete_query)
		cur.execute(query)
		self.conn.commit()

	def updateStockHighLow(self, table, stock, high_price, low_price):
		"""
		updates the 52-week high/low stock values
		"""
		cur = self.conn.cursor()
		delete_query = """
		DELETE FROM {}
		WHERE stock_name=\'{}\';
		""".format(table, stock)

		query = """INSERT INTO {} (stock_name, high_val52wk, low_val52wk) VALUES(%s, %s, %s);""".format(table)

		cur.execute(delete_query)

		cur.execute(query, (stock, high_price, low_price))

		self.conn.commit()
		
		# query = """
		# INSERT INTO {} (stock_name, high_val52wk, low_val52wk) VALUES(
		# \'{}\', {}, {});
		# """.format(table, stock, high_price, low_price)
		# cur.execute(delete_query)
		# cur.execute(query)
		self.conn.commit()

	def fetchInsertStockLoop(self, sleeptime=1):
		"""
		main loop for fetching and inserting stocks
		"""
		while True:
			stock_updates = self.stock_fetcher.fetchAllPrices()
			for stock, price in stock_updates['prices'].items():
				self.insertStock("stock_prices", stock_updates['timestamp'], stock, price)
			time.sleep(sleeptime)

	def fetchUpdateImageURLLoop(self, sleeptime=1):
		"""
		main loop for fetching and updating logo URLs
		"""
		while True:
			image_updates = self.stock_fetcher.fetchAllImages()
			for stock, url in image_updates.items():
				self.updateStockURL("stock_image_urls", stock, url)
			time.sleep(sleeptime)

	def fetchUpdateHighLowLoop(self, sleeptime=1):
		"""
		main loop for fetching and updating 52-week high/low values
		"""
		while True:
			high_low = self.stock_fetcher.fetchAllHighLow()
			for stock, (high, low) in high_low.items():
				self.updateStockHighLow("stock_highlow", stock, high, low)
			time.sleep(sleeptime)

def main():
	stocks_to_fetch = ['GE', 'AMZN', 'NVDA', 'INTC', 'AAPL', 'NFLX']
	stock_fetcher = IEXStockFetcher(stocks_to_fetch)
	conn = psycopg2.connect("dbname=stocks user=ubuntu")
	manager = PostgreSQLStockManager(conn, stock_fetcher)

	stock_price_thread=Thread(target=partial(manager.fetchInsertStockLoop, 5))
	image_url_thread=Thread(target=partial(manager.fetchUpdateImageURLLoop, 5000))
	high_low_thread=Thread(target=partial(manager.fetchUpdateHighLowLoop, 5000))

	stock_price_thread.start()
	image_url_thread.start()
	high_low_thread.start()

	stock_price_thread.join()
	image_url_thread.join()
	high_low_thread.join()

if __name__ == '__main__':
	main()
