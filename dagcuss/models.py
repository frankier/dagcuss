import os
import socket
import logging

from bulbs.rexster import Graph, Config
from bulbs.model import (Node, Relationship, NodeProxy, RelationshipProxy,
                         STRICT)
from bulbs.property import String, Integer, DateTime, Float, Property
from bulbs.utils import current_datetime

from flask import json
from flaskext.login import UserMixin

from dagcuss import app

class RexsterConnectionError(Exception):
    pass

config = Config(app.config['REXSTER_DB_URI'])
if app.config['BULBS_DEBUG']:
    config.set_logger(logging.DEBUG)
try:
    graph = Graph(config)
except socket.error:
    raise RexsterConnectionError(
        "Are you running Rexster on host/port pair in REXSTER_DB_URI?"
    )
graph.scripts.update(os.path.join(os.path.dirname(__file__), 'gremlin.groovy'))

def element_to_model(e, model_cls):
    if e == None:
        return None
    m = model_cls(e._client)
    m._initialize(e._result)
    return m


class User(Node, UserMixin):
    __mode__ = STRICT
    element_type = "user"

    username = String(nullable=False, unique=True)
    password = String(nullable=False)
    joined = DateTime(default=current_datetime, nullable=False)
    active = Integer(nullable=False)

    def get_id(self):
        return self.username

    def is_active(self):
        return self.active

class PostProxy(NodeProxy):
    def create(self, _data=None, **kwds):
        # TODO: Convert asserts to appropriate exceptions
        from dagcuss import dynagraph
        is_root = ((_data and 'root' in _data and _data['root']) or
                   ('root' in kwds and kwds['root']))
        if _data and 'parents' in data:
            parents = _data['parents']
            del _data['parents']
        elif 'parents' in kwds:
            parents = kwds['parents']
            del kwds['parents']
        else:
            # Root has no parents
            assert is_root
            parents = []
        if is_root:
            # Only one root
            assert len(list(graph.posts.index.lookup(root=1))) == 0
        post = NodeProxy.create(self, _data, **kwds)
        replies = []
        for parent in parents:
            replies.append(graph.replies.create(parent, post))
        dynagraph.client(
            insert_node=(post.eid,),
            insert_edge=tuple({
                                'id': reply.eid,
                                'from_id': reply.outV().eid,
                                'to_id': reply.inV().eid,
                              } for reply in replies))
        return post

class Post(Node):
    __mode__ = STRICT
    element_type = "post"

    title = String(nullable=False)
    body = String(nullable=False)
    at = DateTime(default=current_datetime, nullable=False)
    root = Integer(default=0, nullable=False)

    x = Float(default=0, nullable=True)
    y = Float(default=0, nullable=True)

    tile_x = Integer(default=0, nullable=True)
    tile_y = Integer(default=0, nullable=True)

    @classmethod 
    def get_proxy_class(cls):
        return PostProxy

    def parents(self):
        return sorted([element_to_model(e, Post) for e in self.inV("reply")],
                      key=lambda e: e.at, reverse=True)

    def children(self):
        return sorted([element_to_model(e, Post) for e in self.outV("reply")],
                      key=lambda e: e.at, reverse=True)

    def poster(self):
        return [element_to_model(e) for e in self.InV("posted")]

    def has_ancestor_any(self, needles):
        # TODO: Use aggregate/exclude to avoid searching the same parts of the
        # tree twice
        script = graph.scripts.get('has_ancestor_any')
        params = {'id': self.eid,
                  'needle_ids': [needle.eid for needle in needles]}
        items = list(graph.gremlin.query(script, params))
        if len(items) > 0:
            return items[0]
        else:
            return None

    def save(self):
        self.tile_x = (self.x + app.config['TILE_SIZE'] / 2) // app.config['TILE_SIZE']
        self.tile_y = (self.y + app.config['TILE_SIZE'] / 2) // app.config['TILE_SIZE']
        super(Post, self).save()

    def __unicode__(self):
        result = unicode(self.eid)
        if self.title:
            result += " [%s]" % (unicode(self.title),)
        result += " posted on %s" % (unicode(self.at),)
        return result


class Posted(Relationship):
    # user 1 -> 0..* post
    __mode__ = STRICT
    label = "posted"


class Marked(Relationship):
    # user 1 -> 0..9 post
    __mode__ = STRICT
    label = "marked"

    color = Integer(nullable=False)


class PointList(Property):
    python_type = list

    def to_db(self,type_system,value):
        return json.dumps(value)

    def to_python(self,type_system,value):
        return json.loads(value)


class Reply(Relationship):
    # post_a 0    -> 1    post_b | if post_b.root
    # post_a 1..3 -> 0..* post_b | otherwise
    __mode__ = STRICT
    label = "reply"

    pos = PointList(default=None, nullable=True)

    def __eq__(self, other):
        return other and self.eid == other.eid

    def __neq__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return self.eid

    def get_graphviz_pos(self):
        if self.pos == None:
            return None
        return ' '.join(','.join(str(scalar) for scalar in point) for point in self.pos)

    def set_graphviz_pos(self, graphviz_pos):
        self.pos = [tuple(float(scalar) for scalar in point.split(',')) for point in graphviz_pos.split()]

graph.add_proxy("users", User)
graph.add_proxy("posts", Post)
graph.add_proxy("posted", Posted)
graph.add_proxy("replies", Reply)
