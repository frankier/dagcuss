#!/usr/bin/env python2
from flaskext.script import Shell, Server, Manager
from dagcuss import app

manager = Manager(app)
manager.add_command("runserver", Server())
manager.add_command("shell", Shell())

if __name__ == "__main__":
    manager.run()
