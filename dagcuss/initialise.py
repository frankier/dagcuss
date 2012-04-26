#!/usr/bin/env python2
import sys
from dagcuss.models import graph

def database(testdata):
    welcome = graph.posts.create(title="Welcome to DAGcuss", body="Welcome.", root=1)

    if testdata:
        reply = graph.posts.create(title="Example reply", body="Lorem ipsum.", parents=[welcome])
        user = graph.users.create(username="user",
                                password="pass",
                                email="@",
                                active=1)
