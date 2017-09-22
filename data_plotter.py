from bokeh.plotting import figure, curdoc, show
from bokeh.models.sources import ColumnDataSource
import pandas as pd
import psycopg2

# p = figure(toolbar_location=None)
p = figure()

conn = psycopg2.connect("dbname=stocks user=ajpryor")
df = pd.read_sql("""
	SELECT * FROM stock_prices
	WHERE stock_name IN ('GE', 'AMZN', 'GOOG', 'TSLA', 'AAPL', 'NFLX');
	""", conn)

print(df.head(1000))
line_colors = ['red','green','black','cyan','firebrick','olive']
line_dashes = ['solid','dashed','dotted','dashdot','solid','solid']

grouped = df.groupby('stock_name')
ys = [grouped.get_group(stock)['price'] for stock in df.stock_name.unique()]
for i, y in enumerate(ys):
	p.line(x=list(range(len(y))),
	y=y,
	line_alpha=1,
	line_color=line_colors[i],
	line_dash=line_dashes[i],
	line_width=4)

show(p)
