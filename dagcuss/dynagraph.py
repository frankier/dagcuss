import os, sys
import zmq
import blosc
import cPickle as pickle
import asyncsubprocess
import pygraphviz
from logging import debug, error
from flask import json

from dagcuss.models import graph, element_to_model, Reply
from dagcuss import app

# TODO: 
# * Use logging module for logging
# * Refine settings for logging
# * See about factoring out some code from longer functions
# * Pycrust, pep8
# * Review code in Dynagraph class

dot_node_attrs = {
    "shape": "circle",
    "width": "30.0", # (radius + border) * 2
    "height": "30.0"
}

def send_obj(socket, obj, flags=0):
    p = pickle.dumps(obj, -1)
    z = blosc.compress(p, 1)
    return socket.send(z, flags=flags)

def recv_obj(socket, flags=0):
    z = socket.recv(flags)
    p = blosc.decompress(z)
    return pickle.loads(p)

def database_to_dot():
    dot_graph = pygraphviz.AGraph(directed=True, strict=False)
    for post in graph.posts.get_all():
        if post.x != None and post.y != None:
            dot_graph.add_node('n_%s' % (post.eid,), pos="%s,%s" % (post.x, post.y), **dot_node_attrs)
        else:
            dot_graph.add_node('n_%s' % (post.eid,), **dot_node_attrs)
        for relationship in post.outE():
            print "relationship.pos", relationship.pos
            relationship = element_to_model(relationship, Reply)
            if relationship.pos != None:
                print "relationship.pos", relationship.pos
                strpos = relationship.get_graphviz_pos()
                dot_graph.add_edge('n_%s' % (relationship.outV().eid,), 'n_%s' % (relationship.inV().eid,), 'e_%s' % (relationship.eid,), pos=strpos)
            else:
                dot_graph.add_edge('n_%s' % (relationship.outV().eid,), 'n_%s' % (relationship.inV().eid,), 'e_%s' % (relationship.eid,))
    return dot_graph

def dot_to_database(dot):
    dot_graph = pygraphviz.AGraph(string=dot)
    for node in dot_graph.iternodes():
        node_id = int(node[2:])
        split_pos = node.attr['pos'].split(',')
        x = float(split_pos[0])
        y = float(split_pos[1])
        post = graph.posts.get(node_id)
        if post:
            if post.x != x or post.y != y:
                debug('dot_to_database: moving post with id %s to position %s, %s' % (node_id, x, y))
                post.x = x
                post.y = y
                post.save()
        else:
            error("During flushing dot to database post with id %s wasn't in database" % (node_id,))
    for edge in dot_graph.iteredges():
        edge_id = int(edge.attr['id'][2:])
        relationship = graph.replies.get(edge_id)
        relationship = element_to_model(relationship, Reply)
        if relationship:
            if relationship.get_graphviz_pos() != edge.attr['pos']:
                debug('dot_to_database: moving relationship with id %s to position %s' % (edge_id, edge.attr['pos']))
                relationship.set_graphviz_pos(edge.attr['pos'])
                relationship.save()
        else:
            error("During flushing dot to database relationship with id %s wasn't in database" % (edge_id,))

def parse_dot_attributes(bits):
    collecting_attributes = False
    in_quotation = False
    attributes = {}
    for bit in bits:
        if bit[0] == '[':
            collecting_attributes = True
            bit = bit[1:]
        if collecting_attributes:
            if in_quotation:
                if bit[-2] == '"':
                    in_quotation = False
                    bit = bit[:-2]
                    quotation.append(bit)
                    attr = " ".join(quotation)
                    attributes[key] = attr
                else:
                    quotation.append(bit)
            else:
                key, attr = bit.split('=', 1)
                if attr[0] == '"':
                    attr = attr[1:]
                    if attr[-2] == '"':
                        attr = attr[:-2]
                        attributes[key] = attr
                    else:
                        quotation = [attr]
                        in_quotation = True
                else:
                    attr = attr[:-1]
                    attributes[key] = attr
    return attributes

def make_dot_attributes(attrs):
    return "[%s]" % " ".join("%s=%s" % (pair[0], pair[1]) for pair in attrs.iteritems())


class DynagraphProcess(object):
    def __init__(self):
        self.process = asyncsubprocess.Popen(app.config['DYNAGRAPH_BIN_PATH'], stdin=asyncsubprocess.PIPE, stdout=asyncsubprocess.PIPE)

    def communicate(self, command):
        self.process.send(command)
        result_str = asyncsubprocess.recv_some(self.process, e=0)
        return result_str

class Dynagraph(object):
    def __init__(self, name):
        self.name = name
        self.process = DynagraphProcess()
        self.process.communicate('open graph %s\n' % (self.name,))
        self.process.communicate('segue graph %s\n' % (self.name,))
        dot_graph = database_to_dot()
        self.process.communicate(dot_graph.to_string() + '\n')
        self.flush_positions_to_database()
        self.to_modify = []

    def move_posts_and_edges(self):
        to_remove = []
        for command in self.to_modify:
            if command[0] == 'node':
                post_to_modify = graph.posts.get(command[1])
                if post_to_modify:
                    to_remove.append(command)
                    debug("moving post id %s to %s, %s" % (command[1], command[2], command[3]))
                    post_to_modify.x = command[2]
                    post_to_modify.y = command[3]
                    post_to_modify.save()
            elif command[0] == 'edge':
                relation_to_modify = element_to_model(graph.replies.get(command[1]), Reply)
                if relation_to_modify:
                    to_remove.append(command)
                    debug("moving edge id %s to %s" % (command[1], command[2]))
                    relation_to_modify.set_graphviz_pos(command[2])
                    relation_to_modify.save()
        for command in to_remove:
            self.to_modify.remove(command)

    def communicate(self, command):
        response = self.process.communicate(command)
        debug("Response:", response)
        for response_command in response.split('\n'):
            bits = response_command.split()
            if len(bits) > 2 and bits[0] in ('insert', 'modify') and bits[1] in ('node', 'edge'):
                attributes = parse_dot_attributes(bits)
                pos = attributes['pos']
                if bits[1] == 'node':
                    node_id = int(bits[3][2:])
                    pos_split = pos.split(',')
                    self.to_modify.append(('node', node_id, float(pos_split[0]), float(pos_split[1])))
                elif bits[1] == 'edge':
                    edge_id = int(bits[3][2:])
                    self.to_modify.append(('edge', edge_id, pos))

    def lock(self):
        self.communicate('lock graph %s\n' % (self.name,))
        debug("done: lock")

    def unlock(self):
        self.communicate('unlock graph %s\n' % (self.name,))
        debug("done: unlock")

    def insert_node(self, node_name):
        self.communicate('insert node %s n_%s %s\n' % (self.name, node_name, make_dot_attributes(dot_node_attrs)))
        debug("done: node")

    def insert_edge(self, edge_name, node_name1, node_name2):
        self.communicate('insert edge %s e_%s n_%s n_%s\n' % (self.name, edge_name, node_name1, node_name2))
        debug("done: edge")

    def delete_node(self, name):
        self.communicate('delete node %s n_%s\n' % (self.name, name))
        debug("done: del")

    def process_remaining_output(self):
        self.process.communicate('')

    def flush_positions_to_database(self):
        self.process_remaining_output()
        response_lines = self.process.communicate('request graph %s\n' % (self.name,)).split('\n')
        dot = '\n'.join(response_lines[1:]) # first line is 'fulfil graph L'
        dot_to_database(dot)
        debug("done: flush positions to database")

    def trace_graph(self):
        self.process_remaining_output()
        debug(self.process.communicate('request graph %s\n' % (self.name,)))
        debug("done: trace graph")

    def trace_to_modify(self):
        self.process_remaining_output()
        debug(self.to_modify)
        debug("done: trace to modify")

def client(insert_node=(), insert_edge=(), delete_node=(), delete_edge=()):
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.connect(app.config['DYNAGRAPH_ZMQ_CLIENT_ADDR'])

    send_obj(socket, {
        'insert_node': insert_node,
        'insert_edge': insert_edge,
        'delete_node': delete_node,
        'delete_edge': delete_edge,
    })

def server():
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(app.config['DYNAGRAPH_ZMQ_SERVER_ADDR'])

    dynagraph = Dynagraph('L')

    while 1:
        message = recv_obj(socket)
        dynagraph.lock()
        for node_id in message['insert_node']:
            dynagraph.insert_node(node_id)
        for edge in message['insert_edge']:
            dynagraph.insert_edge(edge['id'], edge['from_id'], edge['to_id'])
        for node_id in message['delete_node']:
            dynagraph.delete_node(node_id)
        for edge_id in message['delete_edge']:
            dynagraph.delete_edge(edge_id)
        dynagraph.move_posts_and_edges()
        dynagraph.unlock()
