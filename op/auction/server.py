from flask import Flask

app = Flask(__name__, static_url_path='')
from multiprocessing import Process

@app.route('/')
def index():
    return app.send_static_file('index.html')

def server(host, port):
	app.run(host=host, port=port)

def run_server(*args, **kw):
	p = Process(target=server, args=args)
	p.start()
	return p
