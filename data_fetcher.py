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

	# @abc.abstractmethod
	# def fetchAllPrices(self):
		# return NotImplemented

	@abc.abstractmethod
	def fetchPrice(self, stock):
		return NotImplemented

	@abc.abstractmethod
	def fetchImageURL(self, stock):
		return NotImplemented

class IEXStockFetcher(StockFetcher):
	"""
	Fetches stock information using iextrading.com API
	"""

	url_prefix = "https://api.iextrading.com/1.0/stock/"
	url_suffix_price = "/price"
	url_suffix_img = "/logo"

	def __init__(self, stocks):
		super().__init__(stocks)
		# get the image URLs once
		# self.stock_image_urls = {stock:self.fetchImage(stock) for stock in self.stocks}

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

	def fetchPriceInto(self, stock, results=None):
		# helper function to get the price of stock and store in dict
		results[stock] = self.fetchPrice(stock)

	def fetchURLInto(self, url, results=None):
		# helper function to get the price of stock and store in dict
		results[url] = self.fetchImageURL(url)

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

class PostgreSQLStockManager():
	"""
	Records fetched stock data in a postgreSQL table 
	"""

	def __init__(self, conn, stock_fetcher):
		self.conn = conn
		self.stock_fetcher = stock_fetcher

	def insertStock(self, table, timestamp, stock, price):
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

	def insertStockHighLow(self, table, stock, high_price, low_price):
		cur = self.conn.cursor()
		query = """
		INSERT INTO {} (stock_name, high_val52wk, low_val52wk) VALUES(
		\'{}\',
		\'{}\');
		""".format(table, stock, high_price, low_price)
		cur.execute(query)
		self.conn.commit()

	def fetchInsertStockLoop(self, sleeptime=1):
		while True:
			stock_updates = self.stock_fetcher.fetchAllPrices()
			for stock, price in stock_updates['prices'].items():
				self.insertStock("stock_prices", stock_updates['timestamp'], stock, price)
			time.sleep(sleeptime)

	def fetchInsertImageURLLoop(self, sleeptime=1):
		while True:
			print("fetching images")
			image_updates = self.stock_fetcher.fetchAllImages()
			print(image_updates)
			for stock, url in image_updates.items():
				self.updateStockURL("stock_image_urls", stock, url)
			time.sleep(sleeptime)

	# def fetchfetchHighLowLoop(self, sleeptime=1000):
	# 	while True:
	# 		for stock, price in stock_updates['prices'].items():
	# 			self.insertStock("stock_high_low", stock_updates['timestamp'], stock, price)
	# 		time.sleep(sleeptime)
def main():
	stocks_to_fetch = ['GE', 'AMZN', 'GOOG', 'TSLA', 'AAPL', 'NFLX']
	stock_fetcher = IEXStockFetcher(stocks_to_fetch)
	conn = psycopg2.connect("dbname=stocks user=ajpryor")
	manager = PostgreSQLStockManager(conn, stock_fetcher)
	metadata_manager = PostgreSQLStockManager(conn, stock_fetcher)
	for stock in stocks_to_fetch:
		print("Stock URL : " , stock_fetcher.fetchImageURL(stock))

	fast_thread=Thread(target=partial(manager.fetchInsertStockLoop, 5))
	slow_thread=Thread(target=partial(manager.fetchInsertImageURLLoop, 5))

	fast_thread.start()
	slow_thread.start()

	fast_thread.join()
	slow_thread.join()
	# metadata_manager.fetchMetaLoop(5000)

if __name__ == '__main__':
	main()
