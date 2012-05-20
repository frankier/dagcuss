#!/usr/bin/env python2
import sys
import random
from dagcuss.models import graph

def database(test_user, test_replies):
    welcome = graph.posts.create(title="Welcome to DAGcuss", body="Welcome.", root=1)

    if test_user:
        user = graph.users.create(username="user",
                                password="pass",
                                email="@",
                                active=1)

    for i in xrange(test_replies):
        max_parents = random.randint(1, 3)
        candidate_parents = list(graph.posts.get_all())
        parents = []
        for j in xrange(max_parents):
            if len(candidate_parents) == 0:
                break
            parent = random.choice(candidate_parents)
            candidate_parents.remove(parent)
            for candidate_parent in candidate_parents:
                if (parent.has_ancestor_any((candidate_parent,))
                    or candidate_parent.has_ancestor_any((parent,))):
                    candidate_parents.remove(candidate_parent)
            parents.append(parent)
        reply = graph.posts.create(title="Example reply", body="Lorem ipsum.", parents=parents)
