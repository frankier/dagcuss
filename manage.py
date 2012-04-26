#!/usr/bin/env python2
from flaskext.script import Shell, Server, Manager
from dagcuss import app
from dagcuss import dynagraph
from dagcuss import initialise

manager = Manager(app)

@manager.command
def rundynagraph():
    "Runs the Dynagraph zmq powered DAG layout server."
    dynagraph.server()

@manager.command
def dbinit(testdata=False):
    ("Initialises the database with the essential data and optionally some "
    "test data")
    initialise.database(testdata)

manager.add_command("runserver", Server())
manager.add_command("shell", Shell())

if __name__ == "__main__":
    manager.run()
