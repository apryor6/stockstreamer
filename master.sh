#!/bin/bash
python data_fetcher.py &
#bokeh serve data_plotter.py  --allow-websocket-origin=13.59.119.51:5006
nohup bokeh serve stockstreamer.py  --allow-websocket-origin=13.59.119.51:5006 </dev/null >/dev/null 2>&1 &
