#!/usr/bin/env python
"""
A trial implementation of sequence bloom trees, Solomon & Kingsford, 2015.

This is a simple in-memory version where all of the graphs are in
memory at once; to move it onto disk, the graphs would need to be
dynamically loaded for each query.

To try it out, do::

    factory = GraphFactory(ksize, tablesizes, n_tables)
    root = Node(factory)

    graph1 = factory()
    # ... add stuff to graph1 ...
    leaf1 = Leaf("a", graph1)
    root.add_node(leaf1)

For example, ::

    # filenames: list of fa/fq files
    # ksize: k-mer size
    # tablesizes: Bloom filter table sizes
    # n_tables: Number of tables

    factory = GraphFactory(ksize, tablesizes, n_tables)
    root = Node(factory)

    for filename in filenames:
        graph = factory()
        graph.consume_fasta(filename)
        leaf = Leaf(filename, graph)
        root.add_node(leaf)

then define a search function, ::

    def kmers(k, seq):
        for start in range(len(seq) - k + 1):
            yield seq[start:start + k]

    def search_transcript(node, seq, threshold):
        presence = [ node.data.get(kmer) for kmer in kmers(ksize, seq) ]
        if sum(presence) >= int(threshold * len(seq)):
            return 1
        return 0
"""

from __future__ import print_function, unicode_literals, division

from collections import namedtuple, Mapping, defaultdict
from copy import copy
import json
import math
import os
from random import randint
from tempfile import NamedTemporaryFile

import khmer

from .sbt_storage import FSStorage, TarStorage, IPFSStorage, RedisStorage


STORAGES = {
    'TarStorage': TarStorage,
    'FSStorage': FSStorage,
    'IPFSStorage': IPFSStorage,
    'RedisStorage': RedisStorage,
}
NodePos = namedtuple("NodePos", ["pos", "node"])


def GraphFactory(ksize, starting_size, n_tables):
    "Build new nodegraphs (Bloom filters) of a specific (fixed) size."

    def create_nodegraph():
        return khmer.Nodegraph(ksize, starting_size, n_tables)

    return create_nodegraph


class SBT(object):

    def __init__(self, factory, d=2, storage=None):
        self.factory = factory
        self.nodes = defaultdict(lambda: None)
        self.d = d
        self.max_node = 0
        self.storage = storage

    def new_node_pos(self, node):
        while self.nodes[self.max_node] is not None:
            self.max_node += 1
        return self.max_node

    def add_node(self, node):
        pos = self.new_node_pos(node)

        if pos == 0:  # empty tree; initialize w/node.
            n = Node(self.factory, name="internal." + str(pos))
            self.nodes[0] = n
            pos = self.new_node_pos(node)

        # Cases:
        # 1) parent is a Leaf (already covered)
        # 2) parent is a Node (with empty position available)
        #    - add Leaf, update parent
        # 3) parent is a Node (no position available)
        #    - this is covered by case 1
        # 4) parent is None
        #    this can happen with d != 2, in this case create the parent node
        p = self.parent(pos)
        if isinstance(p.node, Leaf):
            # Create a new internal node
            # node and parent are children of new internal node
            n = Node(self.factory, name="internal." + str(p.pos))
            self.nodes[p.pos] = n

            c1, c2 = self.children(p.pos)[:2]

            self.nodes[c1.pos] = p.node
            self.nodes[c2.pos] = node

            for child in (p.node, node):
                child.update(n)
        elif isinstance(p.node, Node):
            self.nodes[pos] = node
            node.update(p.node)
        elif p.node is None:
            n = Node(self.factory, name="internal." + str(p.pos))
            self.nodes[p.pos] = n
            c1 = self.children(p.pos)[0]
            self.nodes[c1.pos] = node
            node.update(n)

        # update all parents!
        p = self.parent(p.pos)
        while p:
            node.update(p.node)
            p = self.parent(p.pos)

    def find(self, search_fn, *args, **kwargs):
        matches = []
        visited, queue = set(), [0]
        while queue:
            node_p = queue.pop(0)
            node_g = self.nodes[node_p]
            if node_g is None:
                continue

            if node_p not in visited:
                visited.add(node_p)
                if search_fn(node_g, *args):
                    if isinstance(node_g, Leaf):
                        matches.append(node_g)
                    elif isinstance(node_g, Node):
                        if kwargs.get('dfs', True):  # defaults search to dfs
                            for c in self.children(node_p):
                                queue.insert(0, c.pos)
                        else: # bfs
                            queue.extend(c.pos for c in self.children(node_p))
        return matches

    def parent(self, pos):
        if pos == 0:
            return None
        p = int(math.floor((pos - 1) / self.d))
        return NodePos(p, self.nodes[p])

    def children(self, pos):
        return [self.child(pos, c) for c in range(self.d)]

    def child(self, parent, pos):
        cd = self.d * parent + pos + 1
        return NodePos(cd, self.nodes[cd])

    def save(self, tag, storage=None):
        version = 3

        fn = tag + '.sbt.json'

        if storage is None:
            # default storage
            dirname = os.path.abspath(os.path.dirname(fn))
            storage = FSStorage(dirname)

        backend = [k for (k, v) in STORAGES.items() if v == type(storage)][0]

        info = {}
        info['d'] = self.d
        info['version'] = version
        info['storage'] = {
            'backend': backend,
            'args': storage.init_args()
        }

        structure = {}
        for i, node in iter(self):
            if node is None:
                continue

            data = {
                # TODO: start using md5sum instead?
                'filename': os.path.basename(node.name),
                'name': node.name
            }
            if isinstance(node, Leaf):
                data['metadata'] = node.metadata

            node.storage = storage

            data['filename'] = node.save(data['filename'])
            structure[i] = data

        info['nodes'] = structure
        with open(fn, 'w') as fp:
            json.dump(info, fp)

        return fn

    @classmethod
    def load(cls, sbt_name, leaf_loader=None, storage=None):
        dirname = os.path.dirname(sbt_name)
        sbt_name = os.path.basename(sbt_name)

        loaders = {
            1: cls._load_v1,
            2: cls._load_v2,
            3: cls._load_v3,
        }

        # @CTB hack: check to make sure khmer Nodegraph supports the
        # correct methods.
        x = khmer.Nodegraph(1, 1, 1)
        try:
            x.count(10)
        except TypeError:
            raise Exception("khmer version is too old; need >= 2.1.")

        if leaf_loader is None:
            leaf_loader = Leaf.load

        sbt_fn = sbt_name
        if not sbt_fn.endswith('.sbt.json'):
            sbt_fn = sbt_fn + '.sbt.json'
        with open(os.path.join(dirname, sbt_fn)) as fp:
            jnodes = json.load(fp)

        version = 1
        if isinstance(jnodes, Mapping):
            version = jnodes['version']

        if storage is None:
            storage = FSStorage('.')

        return loaders[version](jnodes, leaf_loader, dirname, storage)

    @staticmethod
    def _load_v1(jnodes, leaf_loader, dirname, storage):

        if jnodes[0] is None:
            # TODO error!
            raise ValueError("Empty tree!")

        sbt_nodes = defaultdict(lambda: None)

        sample_bf = os.path.join(dirname, jnodes[0]['filename'])
        ksize, tablesize, ntables = khmer.extract_nodegraph_info(sample_bf)[:3]
        factory = GraphFactory(ksize, tablesize, ntables)

        for i, jnode in enumerate(jnodes):
            if jnode is None:
                continue

            jnode['filename'] = os.path.join(dirname, jnode['filename'])

            if 'internal' in jnode['name']:
                jnode['factory'] = factory
                sbt_node = Node.load(jnode, storage)
            else:
                sbt_node = leaf_loader(jnode, storage)

            sbt_nodes[i] = sbt_node

        tree = SBT(factory)
        tree.nodes = sbt_nodes

        return tree

    @classmethod
    def _load_v2(cls, info, leaf_loader, dirname, storage):
        nodes = {int(k): v for (k, v) in info['nodes'].items()}

        if nodes[0] is None:
            raise ValueError("Empty tree!")

        sbt_nodes = defaultdict(lambda: None)

        sample_bf = os.path.join(dirname, nodes[0]['filename'])
        k, size, ntables = khmer.extract_nodegraph_info(sample_bf)[:3]
        factory = GraphFactory(k, size, ntables)

        for k, node in nodes.items():
            if node is None:
                continue

            node['filename'] = os.path.join(dirname, node['filename'])

            if 'internal' in node['name']:
                node['factory'] = factory
                sbt_node = Node.load(node, storage)
            else:
                sbt_node = leaf_loader(node, storage)

            sbt_nodes[k] = sbt_node

        tree = cls(factory, d=info['d'])
        tree.nodes = sbt_nodes

        return tree

    @classmethod
    def _load_v3(cls, info, leaf_loader, dirname, storage):
        nodes = {int(k): v for (k, v) in info['nodes'].items()}

        if nodes[0] is None:
            raise ValueError("Empty tree!")

        sbt_nodes = defaultdict(lambda: None)

        klass = STORAGES[info['storage']['backend']]
        storage = klass(**info['storage']['args'])

        with NamedTemporaryFile() as sample_bf:
            sample_bf.write(storage.load(nodes[0]['filename']))
            sample_bf.file.flush()
            k, size, ntables = khmer.extract_nodegraph_info(sample_bf.name)[:3]

        factory = GraphFactory(k, size, ntables)

        for k, node in nodes.items():
            if node is None:
                continue

            if 'internal' in node['name']:
                node['factory'] = factory
                sbt_node = Node.load(node, storage)
            else:
                sbt_node = leaf_loader(node, storage)

            sbt_nodes[k] = sbt_node

        tree = cls(factory, d=info['d'], storage=storage)
        tree.nodes = sbt_nodes

        return tree

    def print_dot(self):
        print("""
        digraph G {
        nodesep=0.3;
        ranksep=0.2;
        margin=0.1;
        node [shape=ellipse];
        edge [arrowsize=0.8];
        """)

        for i, node in list(self.nodes.items()):
            if isinstance(node, Node):
                print('"{}" [shape=box fillcolor=gray style=filled]'.format(
                      node.name))
                for j, child in self.children(i):
                    if child is not None:
                        print('"{}" -> "{}"'.format(node.name, child.name))
        print("}")

    def print(self):
        visited, stack = set(), [0]
        while stack:
            node_p = stack.pop()
            node_g = self.nodes[node_p]
            if node_p not in visited and node_g is not None:
                visited.add(node_p)
                depth = int(math.floor(math.log(node_p + 1, self.d)))
                print(" " * 4 * depth, node_g)
                if isinstance(node_g, Node):
                    stack.extend(c.pos for c in self.children(node_p)
                                       if c.pos not in visited)

    def __iter__(self):
        for i, node in self.nodes.items():
            yield (i, node)

    def leaves(self):
        return [c for c in self.nodes.values() if isinstance(c, Leaf)]

    def combine(self, other):
        larger, smaller = self, other
        if len(other.nodes) > len(self.nodes):
            larger, smaller = other, self

        n = Node(self.factory, name="internal.0", storage=self.storage)
        larger.nodes[0].update(n)
        smaller.nodes[0].update(n)
        new_nodes = defaultdict(lambda: None)
        new_nodes[0] = n

        levels = int(math.ceil(math.log(len(larger.nodes), self.d))) + 1
        current_pos = 1
        n_previous = 0
        n_next = 1
        for level in range(1, levels + 1):
            for tree in (larger, smaller):
                for pos in range(n_previous, n_next):
                    if tree.nodes[pos] is not None:
                        new_node = copy(tree.nodes[pos])
                        if isinstance(new_node, Node):
                            # An internal node, we need to update the name
                            new_node.name = "internal.{}".format(current_pos)
                        new_nodes[current_pos] = new_node
                    else:
                        del tree.nodes[pos]
                    current_pos += 1
            n_previous = n_next
            n_next = n_previous + int(self.d ** level)
            current_pos = n_next

        # reset max_node, next time we add a node it will find the next
        # empty position
        self.max_node = 2

        # TODO: do we want to return a new tree, or merge into this one?
        self.nodes = new_nodes
        return self


class Node(object):
    "Internal node of SBT."

    def __init__(self, factory, name=None, path=None, storage=None):
        self.name = name
        self.storage = storage
        self._factory = factory
        self._data = None
        self._path = path

    def __str__(self):
        return '*Node:{name} [occupied: {nb}, fpr: {fpr:.2}]'.format(
                name=self.name, nb=self.data.n_occupied(),
                fpr=khmer.calc_expected_collisions(self.data, True, 1.1))

    def save(self, path):
        # We need to do this tempfile dance because khmer only load
        # data from files.
        with NamedTemporaryFile(suffix=".gz") as f:
            self.data.save(f.name)
            f.file.flush()
            f.file.seek(0)
            return self.storage.save(path, f.read())

    @property
    def data(self):
        if self._data is None:
            if self._path is None:
                self._data = self._factory()
            else:
                data = self.storage.load(self._path)
                # We need to do this tempfile dance because khmer only load
                # data from files.
                with NamedTemporaryFile(suffix=".gz") as f:
                    f.write(data)
                    f.file.flush()
                    self._data = khmer.load_nodegraph(f.name)
        return self._data

    @data.setter
    def data(self, new_data):
        self._data = new_data

    @staticmethod
    def load(info, storage=None):
        new_node = Node(info['factory'],
                        name=info['name'],
                        path=info['filename'],
                        storage=storage)
        return new_node

    def update(self, parent):
        parent.data.update(self.data)


class Leaf(object):
    def __init__(self, metadata, data=None, name=None, storage=None, path=None):
        self.metadata = metadata

        if name is None:
            name = metadata
        self.name = name

        self.storage = storage

        self._data = data
        self._path = path

    def __str__(self):
        return '**Leaf:{name} [occupied: {nb}, fpr: {fpr:.2}] -> {metadata}'.format(
                name=self.name, metadata=self.metadata,
                nb=self.data.n_occupied(),
                fpr=khmer.calc_expected_collisions(self.data, True, 1.1))

    @property
    def data(self):
        if self._data is None:
            data = self.storage.load(self._path)
            # We need to do this tempfile dance because khmer only load
            # data from files.
            with NamedTemporaryFile(suffix=".gz") as f:
                f.write(data)
                f.file.flush()
                self._data = khmer.load_nodegraph(f.name)
        return self._data

    @data.setter
    def data(self, new_data):
        self._data = new_data

    def save(self, path):
        # We need to do this tempfile dance because khmer only load
        # data from files.
        with NamedTemporaryFile(suffix=".gz") as f:
            self.data.save(f.name)
            f.file.flush()
            f.file.seek(0)
            return self.storage.save(path, f.read())

    def update(self, parent):
        parent.data.update(self.data)

    @classmethod
    def load(cls, info, storage=None):
        return cls(info['metadata'],
                   name=info['name'],
                   path=info['filename'],
                   storage=storage)


def filter_distance( filter_a, filter_b, n=1000 ) :
    """
    Compute a heuristic distance per bit between two Bloom
    filters.

    filter_a : First filter
    filter_b : Second filter
    n        : Number of positions to compare (in groups of 8)
    """
    from numpy import array

    A = filter_a.graph.get_raw_tables()
    B = filter_b.graph.get_raw_tables()
    distance = 0
    for q,p in zip( A, B ) :
        a = array( q, copy=False )
        b = array( p, copy=False )
        for i in map( lambda x : randint( 0, len(a) ), range(n) ) :
            distance += sum( map( int, [ not bool((a[i]>>j)&1)
                                           ^ bool((b[i]>>j)&1)
                                         for j in range(8) ] ) )
    return distance / ( 8.0 * len(A) * n )
