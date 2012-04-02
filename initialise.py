#!/usr/bin/env python2
import sys
from dagcuss.models import graph

frm = graph.posts.create(title="Welcome to DAGcuss", body="Welcome.", root=1)

if len(sys.argv) > 1 and sys.argv[1] == 'testdata':
    to = graph.posts.create(title="Example reply", body="Lorem ipsum.")
    graph.replies.create(frm, to)
    user = graph.users.create(username="user", password="pass", email="@", active=1)
