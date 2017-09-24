from bokeh.plotting import figure, curdoc, show
from bokeh.models.sources import ColumnDataSource
from bokeh.models import Range1d, Legend, NumeralTickFormatter, DatetimeTickFormatter, Title
from bokeh.models.tools import PanTool, BoxZoomTool, WheelZoomTool, ResetTool
from bokeh.layouts import row
from bokeh.palettes import Dark2

import datetime
import psycopg2
import pandas as pd
import numpy as np

tools = [PanTool(), BoxZoomTool(), ResetTool(), WheelZoomTool()]

time_today = (datetime.datetime.today()-datetime.datetime(1970,1,1)).total_seconds()
time_now = (datetime.datetime.today()-datetime.datetime(1970,1,1)).total_seconds()
p = figure(title="STOCKSTREAMER v0.0", tools=tools, plot_width=1000,
 y_range=Range1d(-50, 1200), x_range=Range1d(time_today-10000, time_now),
 plot_height=680,toolbar_location='below', toolbar_sticky=False)

# set labels
p.yaxis.axis_label = "Price ($US)"
p.yaxis.axis_label_text_font_size = '12pt'
p.yaxis[0].formatter = NumeralTickFormatter(format="$0")
p.xaxis[0].formatter = DatetimeTickFormatter()

p.background_fill_color = "#F0F0F0"
p.title.text_font = "times"
p.title.text_font_size = "16pt"

info_label = Title(text='*Bounding boxes indicate 52-week high/low', align='left',
	text_font_size='10pt', text_font='times', text_font_style='italic', offset=25)
p.add_layout(info_label, 'below')


conn = psycopg2.connect("dbname=stocks user=ubuntu")
line_colors = ['red','green','black','cyan','firebrick','olive']
line_colors = Dark2[6]
line_dashes = ['solid']*6



# get stock image urls and convert to dict
image_urls = pd.read_sql("""
	SELECT * FROM stock_image_urls;
	""", conn)
image_urls.set_index('stock_name', inplace=True)
# image_urls = {stock:url for (stock, url) in zip(image_urls['stock_name'], image_urls['image_url'])}


stock_highlow = pd.read_sql("""
	SELECT * FROM stock_highlow;
	""", conn)
stock_highlow.set_index('stock_name', inplace=True)
# stock_highlow = {stock:(high, low) for (stock, (high, low)) in zip(stock_highlow['stock_name'], stock_highlow['image_url'])}

def get_data():
	df = pd.read_sql("""
	SELECT * FROM stock_prices
	WHERE time >= NOW() - '7 day'::INTERVAL
	""", conn)

	# convert to absolute time in seconds
	df['time_s'] = df['time'].apply(lambda x: (x-datetime.datetime(1970,1,1)).total_seconds())

	grouped = df.groupby('stock_name')
	unique_names = df.stock_name.unique()
	# unique_names=['GE', 'AMZN', 'NVDA', 'INTC', 'AAPL', 'NFLX']
	ys = [grouped.get_group(stock)['price'] for stock in unique_names]
	xs = [grouped.get_group(stock)['time'] for stock in unique_names]
	max_ys = [np.max(y) for y in ys]
	return (xs, ys, max_ys, unique_names)

xs, ys, max_ys, unique_names = get_data()
lines = []
circles = []
recs = []
for i, (x, y, max_y, name) in enumerate(zip(xs, ys, max_ys, unique_names)):
	lines.append(p.line(x=x,
	    y=y,
	    line_alpha=1,
	    line_color=line_colors[i],
	    line_dash=line_dashes[i],
	    line_width=2))
	circles.append(p.circle(x=x,
	    y=y,
	    line_alpha=1,
	    radius=0.1,
	    line_color=line_colors[i],
	    fill_color=line_colors[i],
	    line_dash=line_dashes[i],
	    line_width=1))

	source = ColumnDataSource(dict(y=[(stock_highlow.loc[name, 'high_val52wk'] + stock_highlow.loc[name, 'low_val52wk'])/2],
							   left=[x.min()],
		                       right=[x.max()],
		                       height=[[(stock_highlow.loc[name, 'high_val52wk'] - stock_highlow.loc[name, 'low_val52wk'])]],
		                       fill_alpha=[0.1],
		                       fill_color=[line_colors[i]],
		                       line_color=[line_colors[i]]))
	# source = ColumnDataSource(dict(y=[max_y],
	# 							   left=[x.min()],
	# 		                       right=[x.max()],
	# 		                       height=[50],
	# 		                       fill_alpha=[0.2],
	# 		                       fill_color=[line_colors[i]],
	# 		                       line_color=[line_colors[i]]))
	recs.append(p.hbar(y='y', left='left', right='right', height='height', fill_alpha='fill_alpha',fill_color='fill_color',
		line_alpha=0.1, line_color='line_color', line_dash='solid', line_width=0.1, source=source))

legend = Legend(items=[(stock, [l]) for stock, l in zip(unique_names, lines)], location=(0,0), orientation='horizontal')
N = len(unique_names)
latest_timestamp = np.max(xs[0])
source = ColumnDataSource(dict(
    url = [image_urls.loc[name, 'image_url'] for name in unique_names],
    x1  = [i.min() for i in xs],
    y1  = max_ys,
    w1  = [32]*N,
    h1  = [32]*N,
))

p.x_range=Range1d(-256, xs[0].max())
image_plot = p.image_url(url='url' ,x='x1', y='y1', w='w1', h='h1',source=source,
 anchor="center", global_alpha=0.7, w_units='screen', h_units='screen')


def update_figure():
	xs, ys, max_ys, unique_names = get_data()
	for i, (x, y, max_y) in enumerate(zip(xs, ys, max_ys)):
		lines[i].data_source.data.update(x=x, y=y)
		circles[i].data_source.data.update(x=x, y=y)
		recs[i].data_source.data.update(left=[x.min()], right=[x.max()])

time_range = xs[0].max() - xs[0].min()
p.x_range.start=np.min(xs[0]) - time_range*0.1
p.x_range.end=np.max(xs[0])

update_figure()
p.add_layout(legend, 'below')
curdoc().add_root(p)
curdoc().add_periodic_callback(update_figure, 5000)
