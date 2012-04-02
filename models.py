from bulbs.rexster import Graph, Config
from bulbs.model import Node, Relationship
from bulbs.property import Property, String, Integer, DateTime
from bulbs.utils import current_datetime
from flaskext.login import UserMixin

config = Config('http://localhost:8182/graphs/dagcussdb')
config.label_var = 'rel_label'
graph = Graph(config)

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


class Post(Node):
    element_type = "post"

    title = String(nullable=False)
    body = String(nullable=False)
    at = DateTime(default=current_datetime, nullable=False)
    root = Integer(default=0, nullable=False)

    def parents(self):
        return sorted([element_to_model(e, Post) for e in self.inV("reply")], key=lambda e: e.at, reverse=True)

    def children(self):
        return sorted([element_to_model(e, Post) for e in self.outV("reply")], key=lambda e: e.at, reverse=True)

    def poster(self):
        return [element_to_model(e) for e in self.InV("posted")]

    def has_ancestor_any(self, needles):
        # TODO: Use aggregate/exclude to avoid searching the same parts of the tree twice
        script = (
"""
needles = needle_ids.collect {g.v(it)}
g.v(id).as('get_parents').inE.filter{it.label == 'reply'}.outV.loop('get_parents'){!needles.contains(it.object)}{needles.contains(it.object)}.id
"""[1:-1]
        )
        params = {'id': self.eid, 'needle_ids': [needle.eid for needle in needles]}
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
    rel_label = "posted"


class Marked(Relationship):
    # user 1 -> 0..9 post
    rel_label = "marked"

    color = Integer(nullable=False)


class Reply(Relationship):
    # post_a 0    -> 1    post_b | if post_b.root
    # post_a 1..3 -> 0..* post_b | otherwise
    rel_label = "reply"

graph.add_proxy("users", User)
graph.add_proxy("posts", Post)
graph.add_proxy("posted", Posted)
graph.add_proxy("replies", Reply)
