from bokeh.plotting import figure, curdoc, show
from bokeh.models.sources import ColumnDataSource
from bokeh.models import Range1d
from bokeh.layouts import row

import datetime
import psycopg2
import pandas as pd
import numpy as np

# p = figure(toolbar_location=None)
p = figure()
p2 = figure()
conn = psycopg2.connect("dbname=stocks user=ubuntu")
line_colors = ['red','green','black','cyan','firebrick','olive']
line_dashes = ['solid','dashed','dotted','dashdot','solid','solid']

image_urls = {'GE'   :  'https://storage.googleapis.com/iex/api/logos/GE.png',
'AMZN'  :  'https://storage.googleapis.com/iex/api/logos/AMZN.png',
'GOOG'  :  'https://storage.googleapis.com/iex/api/logos/GOOG.png',
'TSLA'  :  'https://storage.googleapis.com/iex/api/logos/TSLA.png',
'AAPL'  :  'https://storage.googleapis.com/iex/api/logos/AAPL.png',
'NFLX'  :  'https://storage.googleapis.com/iex/api/logos/NFLX.png'}

def get_data():
	df = pd.read_sql("""
	SELECT * FROM stock_prices
	WHERE stock_name IN ('GE', 'AMZN', 'GOOG', 'TSLA', 'AAPL', 'NFLX')
	AND time >= NOW() - '7 day'::INTERVAL
	""", conn)

	grouped = df.groupby('stock_name')
	unique_names = df.stock_name.unique()
	ys = [grouped.get_group(stock)['price'] for stock in unique_names]
	xs = [list(range(len(y))) for y in ys]

	# xs = [grouped.get_group(stock)['time'] for stock in unique_names]
	max_ys = [np.max(y) for y in ys]
	return (xs, ys, max_ys, unique_names)

xs, ys, max_ys, unique_names = get_data()
lines = []
for i, (x, y) in enumerate(zip(xs, ys)):
	# print("INDI ", (len(x), len(y)))
	lines.append(p.line(x=x,
	    y=y,
	    line_alpha=1,
	    line_color=line_colors[i],
	    line_dash=line_dashes[i],
	    line_width=4))

N = len(image_urls)
latest_timestamp = np.max(xs[0])
source = ColumnDataSource(dict(
    url = [image_urls[name] for name in unique_names],
    x1  = [0]*N,

    y1  = max_ys,
    w1  = [128]*N,
    h1  = [64]*N,
))
# 
p2.x_range = Range1d(-10, 10+32*N)
p2.y_range = Range1d(10, 10+32*N)
# p.x_range = Range1d(-10, 10+32*N)
# p.y_range = Range1d(10, 10+32*N)
image_plot = p.image_url(url='url' ,x='x1', y='y1', w='w1', h='h1',source=source, anchor="center")
image_plot = p2.image_url(url='url' ,x='x1', y='y1', w='w1', h='h1',source=source, anchor="center")

def callback():
	xs, ys, max_ys, unique_names = get_data()
	for i, (x, y) in enumerate(zip(xs, ys)):

		ds = lines[i].data_source
		ds.data = dict(x=x, y=y)


curdoc().add_root(p)
# curdoc().add_root(row(p,p2))
# curdoc().add_root(p2)

curdoc().add_periodic_callback(callback, 500)
