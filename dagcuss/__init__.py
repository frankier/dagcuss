from flask import Flask
app = Flask(__name__)
app.config.from_object('dagcuss.default_settings')
app.config.from_object('dagcuss.settings')

import dagcuss.views
