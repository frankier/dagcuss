#!/usr/bin/env python
import os, sys
import zmq
import asyncsubprocess
import pygraphviz
import logging

from dagcuss.models import graph

tracelevel = 3

def _trace(threshold_level):
    def _inner_trace(*msg):
        if tracelevel >= threshold_level:
            msg = [(m if isinstance(m, str) else repr(m)) for m in msg if m != '']
            print ','.join(msg)
    return _inner_trace

output = _trace(1)
error = _trace(2)
trace = _trace(3)

def database_to_dot():
    digraph = pygraphviz.AGraph(directed=True, strict=False)
    for post in graph.posts.get_all():
        if post.x != None and post.y != None:
            digraph.add_node('n_%s' % (post.eid,), pos="%s,%s" % (post.x, post.y), shape="circle", width="1.0", height="1.0")
        else:
            digraph.add_node('n_%s' % (post.eid,), shape="none", width="0.0", height="0.0")
        for relationship in post.outE():
            if relationship.pos != None:
                digraph.add_edge('n_%s' % (relationship.outV().eid,), 'n_%s' % (relationship.inV().eid,), 'e_%s' % (relationship.eid,), pos=str(relationship.pos))
            else:
                digraph.add_edge('n_%s' % (relationship.outV().eid,), 'n_%s' % (relationship.inV().eid,), 'e_%s' % (relationship.eid,))
    return digraph

def dot_to_database(dot):
    digraph = pygraphviz.AGraph(string=dot)
    for node in digraph.iternodes():
        id = int(node[2:])
        split_pos = node.attr['pos'].split(',')
        x = float(split_pos[0])
        y = float(split_pos[1])
        post = graph.posts.get(id)
        if post:
            if post.x != x or post.y != y:
                trace('dot_to_database: moving post with id %s to position %s, %s' % (id, x, y))
                post.x = x
                post.y = y
                post.save()
        else:
            error("During flushing dot to database post with id %s wasn't in database" % (id,))
    for edge in digraph.iteredges():
        id = int(edge.attr['id'][2:])
        pos = edge.attr['pos']
        try:
            relationship = Relationship.objects.get(id=id)
        except Relationship.DoesNotExist:
            error("During flushing dot to database relationship with id %s wasn't in database" % (id,))
        else:
            if relationship.pos != pos:
                trace('dot_to_database: moving relationship with id %s to position %s' % (id, pos))
                relationship.pos = pos
                relationship.save()

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


class DynagraphProcess(object):
    def __init__(self):
        self.process = asyncsubprocess.Popen('./dynagraph', stdin=asyncsubprocess.PIPE, stdout=asyncsubprocess.PIPE)

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
                try:
                    post_to_modify = Post.objects.get(id=command[1])
                except Post.DoesNotExist:
                    pass
                else:
                    to_remove.append(command)
                    trace("moving post id %s to %s, %s" % (command[1], command[2], command[3]))
                    post_to_modify.x = command[2]
                    post_to_modify.y = command[3]
                    post_to_modify.save()
            elif command[0] == 'edge':
                try:
                    relation_to_modify = Relationship.objects.get(id=command[1])
                except Relationship.DoesNotExist:
                    pass
                else:
                    to_remove.append(command)
                    trace("moving edge id %s to %s" % (command[1], command[2]))
                    relation_to_modify.pos = command[2]
                    relation_to_modify.save()
        for command in to_remove:
            self.to_modify.remove(command)

    def communicate(self, command):
        response = self.process.communicate(command)
        trace("Response:", response)
        for response_command in response.split('\n'):
            bits = response_command.split()
            if len(bits) > 2 and bits[0] in ('insert', 'modify') and bits[1] in ('node', 'edge'):
                attributes = parse_dot_attributes(bits)
                pos = attributes['pos']
                if bits[1] == 'node':
                    id = int(bits[3][1:])
                    pos_split = pos.split(',')
                    self.to_modify.append(('node', id, float(pos_split[0]), float(pos_split[1])))
                elif bits[1] == 'edge':
                    id = int(bits[3][2:])
                    self.to_modify.append(('edge', id, pos))

    def lock(self):
        self.communicate('lock graph %s\n' % (self.name,))
        trace("done: lock")

    def unlock(self):
        self.communicate('unlock graph %s\n' % (self.name,))
        trace("done: unlock")

    def insert_node(self, node_name):
        self.communicate('insert node %s n_%s [shape=circle, width=1, height=1]\n' % (self.name, node_name))
        trace("done: node")

    def insert_edge(self, edge_name, node_name1, node_name2):
        self.communicate('insert edge %s e_%s n_%s n_%s\n' % (self.name, edge_name, node_name1, node_name2))
        trace("done: edge")

    def delete_node(self, name):
        self.communicate('delete node %s n_%s\n' % (self.name, name))
        trace("done: del")

    def process_remaining_output(self):
        self.process.communicate('')

    def flush_positions_to_database(self):
        self.process_remaining_output()
        response_lines = self.process.communicate('request graph %s\n' % (self.name,)).split('\n')
        dot = '\n'.join(response_lines[1:]) # first line is 'fulfil graph L'
        dot_to_database(dot)
        trace("done: flush positions to database")

    def trace_graph(self):
        self.process_remaining_output()
        trace(self.process.communicate('request graph %s\n' % (self.name,)))
        trace("done: trace graph")

    def trace_to_modify(self):
        self.process_remaining_output()
        trace(self.to_modify)
        trace("done: trace to modify")


if __name__ == '__main__':
    import zmq

    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(sys.argv > 1 ? sys.argv[1] : "tcp://localhost:5555")

    dynagraph = Dynagraph('L')

    while 1:
        message = socket.recv()
        dynagraph.lock()
        for node_id in message['insert_node']:
            dynagraph.insert_node(node_id)
        for edge in message['insert_edge']:
            dynagraph.insert_edge(edge['id'], edge['from_id'], edge['to_id'])
        for node_id in message['delete_node']:
            dynagraph.delete_node(node_id)
        for edge_id in message['delete_edge']:
            dynagraph.delete_edge(edge_id)
        dynagraph.unlock()
