# Building an interactive, data-driven web-application using Amazon EC2 and Python

Modern data is generated massively and flows constantly. We want to understand that data, and often we want to understand that data *right now*. Being familiar with methods to produce infrastructure that is capable of processing data on the fly is a useful skill, and a great example of this is building visualization tools that display data as it is generated, allowing you to visualize changes in real time. In this post I'll use Python build such a data visualization tool, specifically a stock ticker. Using [IEX trading's API](https://iextrading.com), we will create a multithreaded service that constantly queries information about stock prices and stores it in a PostgreSQL database. We'll then build an interactive Python application that fetches data from this database using `psychopg2` and visualizes it interactively with `Bokeh`. Finally, we will deploy this application on the Cloud using Amazon Web Services EC2, making our visualization publicly accessible through an elastic ip. All of the code for this can be found [on Github](https://github.com/apryor6/stockstreamer), and you can view the application live [here](http://13.59.160.9:5006/stockstreamer).

## Application Structure

The following diagram illustrates roughly how the logic of our application will flow.

![Diagram of application structure](diagram.png)

A data fetching program written in Python will repeatedly request information from IEX Trading, which provides [a useful API](https://iextrading.com/developer/) for querying information about stocks over the internet. The program will then store this information in a PostgreSQL database, where a second Python application will use that data to generate an interactive visualiation using [`Bokeh`](https://bokeh.pydata.org/en/latest/). `Bokeh` is a powerful visualization framework that links Javascript and Python, allowing objects to be created with relatively simple Python code that are then viewable in a web browser. In its basic form, `Bokeh` uses Python to create HTML and then leaves the Python ecosystem behind. However, we want there to be ongoing communication link between Python and our visualization so that the data can be updated constantly, and this can be accomplished with the additional of a [`Bokeh` server](https://bokeh.pydata.org/en/latest/docs/user_guide/server.html). All of these components can be created in just a few hundred lines of Python and will be contained within a cloud machine on Amazon EC2.

## Setting up the EC2 instance

First we want to get our remote server up and running on the cloud. If you don't already have an account with AWS, create one and then login to the console [here](https://aws.amazon.com/console/). Go to `Services -> EC2` and select `Instances` and click `Launch Instance`. Choose the Ubuntu disk image. Next you'll select the hardware. The free tier is sufficient for this demo, but be aware that such a server won't be particularly responsive with only one core to handle all of the work. This can be improved by upgrading the machine, but be aware that you will be liable for any charges. Click next until "Configure Security Group". Click "Add rule" and choose type "All TCP" and then set Source to "anywhere". This will allow all network traffic to reach our web application. In a proper business application one should take more care with network security, but for this use case it's fine. Click "Launch", then select the drop down and create a new key pair, download it, and launch the instance. This key pair is for authentication purposes, and must be kept secret. You'll need the private key in order to ssh into the EC2 instance, and if you lose it you will be forced to launch a new instance from scratch and recreate the key pair. After a few minutes the Instance State should indicate running from the instance dashboard, and the machine is good to go. 

## Establishing a static ("elastic") IP

Amazon automatically assigns an IP address to each EC2 instance whenever they are started, but by default this is a different dynamically allocated address each time the instance is started. For our web application to be permanently accessible from the same IP, we will need to allocate a static address -- Amazon uses the term elastic IP. From the dashboard, go to "Elastic IP's" and click Allocate new address. Click the newly allocated elastic IP, choose Actions -> Associate address and then select the EC2 instance from the dropdown, and accept. Now if you return to the Instance tab and click the EC2 instance you should see the IPv4 Public IP in the bottom right to reflect the new elastic IP, and even if you stop/start the instance this should remain the same.

## Accessing the instance

To ssh into the instance, the permissions of the first private key file must be modified to be read-only

~~~
chmod 400 mykey.pem
~~~

Where mykey.pem will be replaced with whatever you named the private key file we downloaded earlier. Then we can reach the EC2 instance with 

~~~
ssh ubuntu@[ip-address] -i mykey.pem
~~~

Where [ip-address] should be replaced with the elastic IP of the EC2 instance.

## Configuring the instance

First we have to install some Python and PostgreSQL dependencies
~~~
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.6
sudo apt-get install postgresql postgresql-contrib
sudo apt install python3-pip
pip3 install virtualenv
pip3 install bokeh
pip3 install psycopg2
pip3 install pandas
~~~

Next create a virtualenv and activate it. 
~~~
virtualenv -p python3 py3
source py3/bin/activate
~~~

I like to add the source command to ~/.bashrc so that the virtualenv is activated automatically at each login.

## Configure the database

Because we are setting up our own database, we have to do a little bit of administrative stuff.
~~~
sudo su - postgres
psql
~~~

This will login to the default database, but with sudo privileges. For security, we would like to create another user and access everything through that.

From within `psql`, create a new user and adjust the privileges. 

~~~ sql
CREATE ROLE ubuntu WITH CREATEDB;
ALTER ROLE ubuntu WITH LOGIN;
\password ubuntu;
CREATE DATABASE stocks;
~~~

You'll then be prompted to create a password for the user "ubuntu". Next exit `psql` with "\q", and logout of the superuser with ctr+d so that your prompt returns to something like `ubuntu@#######`. Now if you type `psql stocks` you should be able to login to the new database, and this time under the new account.  

Now we want to create three tables:

	1. stock_price: contains records of stock prices with timestamps
	2. image_url: contains a URL where the company logo for each stock may be found
	3. stock_highlow: contains the 52-week high and low values for the stock 

~~~ sql
CREATE TABLE stock_prices (
stock_name varchar(6),
price decimal,
time timestamp);

CREATE TABLE stock_image_urls(
stock_name varchar(6),
image_url varchar(1024));

CREATE TABLE stock_highlow(
stock_name varchar(6),
high_val52wk decimal,
low_val52wk decimal);
~~~

and that's all we need to do to setup the database - now to build some Python code that will feed it data from the internet.

## Building the data fetcher

First we will need an object that is capable of fetching stock information. Although we are specifically using IEX Trading here, good software practice suggests to encapsulate this behavior in a generalized interface so that if we wanted to support a different API later we could easily drop in a replacement. Here's the basic interface

~~~ python
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
~~~


And now we can create a class that concretely implements these methods specifically for IEX trading

~~~ python
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
~~~

So for each property, an HTTP request is created and JSON data is returned from IEX Trading, which then gets parsed into the right format. The try-except loops are to handle any errors with the request by simply retrying. In production code, there should be a counter that will only retry a finite amount of times before throwing a more dramatic exception.

We will also want some functionality to be able to obtain the values for many stocks. A trivial way to do this would be to loop through the stocks and call `fetchPrice`, but there is a performance issue with that. Each HTTP request will block until it receives a result. If we instead make multiple requests across multiple threads then it is possible for the scheduler to switch to another thread context while waiting for the response, which will dramatically increase the performance of our i/o. So we will loop through the stocks and create a new thread for each that will make the request. Because returning values from Python threads is kind of tricky, we'll instead pass a dictionary into each thread where the result will be placed by a helper function. The full class implementation follows.

~~~ python
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
~~~

Now that we have a class that is capable of acquiring stock data, we need some way to store that. To do that, we'll create a manager object that is responsible for storing results obtained by a StockFetcher into a SQL database. This class could also be created as an abstract base class followed by a concrete implementation of the interface, but considering that the likelihood of swapping database backends for this project is small I'll just directly implement a class. The manager is created with an existing PostgreSQL connection context and will use that context to insert values that it obtains from the StockFetcher.

~~~ python
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
		query = """
		INSERT INTO {} (stock_name, high_val52wk, low_val52wk) VALUES(
		\'{}\', {}, {});
		""".format(table, stock, high_price, low_price)
		cur.execute(delete_query)
		cur.execute(query)
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
~~~

We want to check the stock price pretty frequently, but the 52-week high/low value and logo URL are much less likely to change, so by using the `sleeptime` parameter in our `PostgreSQLStockManager` class we can create a fast and slow loop so that some tasks occur more often as needed.  

To actually use our data fetcher, we now choose a list of stocks, create a couple of objects, and launch the main worker threads.

~~~ python 
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
~~~

This program is an infinite loop and will insert query/insert stock data until the process is killed.

## Creating the Bokeh application

Now that we have a growing database, we can use that data to produce a visualization of stock prices over time. Our `Bokeh` application will make a query to the database and then draw separate lines for each stock. Through use of `curdoc` and `add_periodic_callback`, we can trigger a periodic update of the data so that the plot will adjust to include any new datapoints. 

*As an aside, Bokeh also supports a `stream` method that can be used to update data for a figure. One could alter this code to move the HTTP requests for stock information into a callback function and just have the visualization application fetch its own data, bypassing the database entirely. This could be more performant but at the cost of no longer storing data over time.*

