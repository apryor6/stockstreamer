from bokeh.plotting import figure, curdoc, show
from bokeh.models.sources import ColumnDataSource
from bokeh.models import Range1d, Legend
from bokeh.models.tools import PanTool, BoxZoomTool, WheelZoomTool, ResetTool
from bokeh.layouts import row
from bokeh.palettes import Dark2

import datetime
import psycopg2
import pandas as pd
import numpy as np

tools = [PanTool(), BoxZoomTool(), ResetTool(), WheelZoomTool()]
p = figure(title="STOCKSTREAMER", tools=tools, plot_width=1000, y_range=Range1d(-50, 1100), plot_height=680,toolbar_location='below', toolbar_sticky=False)
# p_imgs = figure(plot_width=512, plot_height=p.plot_height, y_range=p.y_range, toolbar_location=None)
# p_imgs = figure(plot_width=512, plot_height=680 ,toolbar_location=None)

# p = figure(title="STOCKSTREAMER")
p.background_fill_color = "#F0F0F0"
p.title.text_font = "times"
p.title.text_font_size = "16pt"

p.text(x=[0], y=[-50],
 text=['Bounding boxes indicate 52-week high/low'], text_font='times', 
 text_font_size="8pt", text_font_style='italic')

conn = psycopg2.connect("dbname=stocks user=ubuntu")
line_colors = ['red','green','black','cyan','firebrick','olive']
line_colors = Dark2[6]
line_dashes = ['solid']*6


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
circles = []
recs = []
for i, (x, y, max_y, name) in enumerate(zip(xs, ys, max_ys, unique_names)):
	lines.append(p.line(x=x,
	    y=y,
	    line_alpha=1,
	    line_color=line_colors[i],
	    line_dash=line_dashes[i],
	    line_width=5))
	circles.append(p.circle(x=x,
	    y=y,
	    line_alpha=1,
	    radius=0.1,
	    # line_color='black',
	    line_color=line_colors[i],
	    fill_color=line_colors[i],
	    line_dash=line_dashes[i],
	    line_width=1))
	    # legend=name))
	
	source = ColumnDataSource(dict(y=[max_y],
								   left=[x[0]],
			                       right=[x[-1]],
			                       height=[50],
			                       fill_alpha=[0.1],
			                       fill_color=[line_colors[i]],
			                       line_color=[line_colors[i]]))
	recs.append(p.hbar(y='y', left='left', right='right', height='height', fill_alpha='fill_alpha',fill_color='fill_color',
		line_alpha=0.01, line_color='line_color', line_dash='solid', line_width=0.1, source=source))

legend = Legend(items=[(stock, [l]) for stock, l in zip(unique_names, lines)], location=(0,0), orientation='horizontal')
N = len(image_urls)
latest_timestamp = np.max(xs[0])
source = ColumnDataSource(dict(
    url = [image_urls[name] for name in unique_names],
    x1  = [-128]*N,
    y1  = max_ys,
    w1  = [64]*N,
    h1  = [64]*N,
))

p.x_range=Range1d(-256, xs[0][-1])
image_plot = p.image_url(url='url' ,x='x1', y='y1', w='w1', h='h1',source=source,
 anchor="center", global_alpha=0.7, w_units='screen', h_units='screen')
# image_plot = p_imgs.image_url(url='url' ,x='x1', y='y1', w='w1', h='h1',source=source, anchor="center", global_alpha=0.7)


def callback():
	xs, ys, max_ys, unique_names = get_data()
	for i, (x, y, max_y) in enumerate(zip(xs, ys, max_ys)):
		new_data = dict(x=x, y=y)
		ds_lines = lines[i].data_source
		ds_lines.data = new_data
		ds_circle = circles[i].data_source
		ds_circle.data = new_data
		recs[i].data_source.data.update(left=[x[0]], right=[x[-1]])
		p_imgs.y_range = p.y_range



p.add_layout(legend, 'below')
curdoc().add_root(p)
# curdoc().add_root(row(p, p_imgs))
curdoc().add_periodic_callback(callback, 5000)
