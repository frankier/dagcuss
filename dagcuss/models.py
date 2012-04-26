from bulbs.rexster import Graph
from bulbs.model import Node, Relationship, NodeProxy, RelationshipProxy
from bulbs.property import String, Integer, DateTime, Float
from bulbs.utils import current_datetime
from flaskext.login import UserMixin

from dagcuss import app
from bulbs.rexster import Config
config = Config(app.config['REXSTER_DB_URI'])
if app.config['BULBS_DEBUG']:
    import logging
    config.set_logger(logging.DEBUG)
graph = Graph(config)

from dagcuss import dynagraph

def element_to_model(e, model_cls):
    m = model_cls(e._client)
    m._initialize(e._result)
    return m


class User(Node, UserMixin):
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
        if _data and 'parents' in data:
            parents = _data['parents']
            del _data['parents']
        elif 'parents' in kwds:
            parents = kwds['parents']
            del kwds['parents']
        else:
            assert ((_data and 'root' in _data and _data['root']) or
                    ('root' in kwds and kwds['root']))
            parents = []
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
    element_type = "post"

    title = String(nullable=False)
    body = String(nullable=False)
    at = DateTime(default=current_datetime, nullable=False)
    root = Integer(default=0, nullable=False)

    x = Float(default=0, nullable=True)
    y = Float(default=0, nullable=True)

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
        script = (
"""
needles = needle_ids.collect {g.v(it)}
(g.v(id).as('get_parents').inE.filter{it.label == 'reply'}.outV.
loop('get_parents'){!needles.contains(it.object)}
{needles.contains(it.object)}.id)
"""[1:-1]
        )
        params = {'id': self.eid,
                  'needle_ids': [needle.eid for needle in needles]}
        result = graph.client.gremlin(script, params)
        if result.total_size > 0:
            ancestor_id = result.one().data
            return graph.posts.get(ancestor_id)
        else:
            return None

    def __unicode__(self):
        result = unicode(self.eid)
        if self.title:
            result += " [%s]" % (unicode(self.title),)
        result += " posted on %s" % (unicode(self.at),)
        return result


class Posted(Relationship):
    # user 1 -> 0..* post
    label = "posted"


class Marked(Relationship):
    # user 1 -> 0..9 post
    label = "marked"

    color = Integer(nullable=False)


class Reply(Relationship):
    # post_a 0    -> 1    post_b | if post_b.root
    # post_a 1..3 -> 0..* post_b | otherwise
    label = "reply"

    pos = String(default="", nullable=False)

graph.add_proxy("users", User)
graph.add_proxy("posts", Post)
graph.add_proxy("posted", Posted)
graph.add_proxy("replies", Reply)
