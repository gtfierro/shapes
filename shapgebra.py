import rdflib
import pyshacl
from rdflib.collection import Collection
from rdflib import URIRef, BNode, Literal, Namespace
from typing import List, Union, Optional, Any
from collections.abc import Iterable
from collections import deque


SH = Namespace("http://www.w3.org/ns/shacl#")
G36 = Namespace("urn:ashrae/g36/4.1/vav-cooling-only/")


def drop_none(l: List[Optional[Any]]) -> List[Any]:
    return [x for x in l if x is not None]


def all_shapes(graph: rdflib.Graph) -> List[Union[URIRef, BNode]]:
    q = """SELECT ?s WHERE {
        { ?s a sh:NodeShape }
        UNION
        { ?s a sh:PropertyShape }
        UNION
        { ?x sh:node ?s }
        UNION
        { ?x sh:property ?s }
    }"""
    return [x[0] for x in graph.query(q)]


class ShapeGraph:
    graph: rdflib.Graph
    nodes: List["SHACLNode"]

    def __init__(self, graph: rdflib.Graph):
        self.graph = graph
        self.nodes = []

        for ns in self.graph.subjects(predicate=rdflib.RDF.type, object=rdflib.SH.NodeShape):
            assert isinstance(ns, (URIRef, BNode))
            node = NodeShape.parse(graph, ns)
            if node is not None:
                self.nodes.append(node)

        for ns in self.graph.subjects(predicate=rdflib.RDF.type, object=rdflib.SH.PropertyShape):
            assert isinstance(ns, (URIRef, BNode))
            node = PropertyShape.parse(graph, ns)
            if node is not None:
                self.nodes.append(node)

        for ns in self.graph.objects(predicate=rdflib.SH.node):
            assert isinstance(ns, (URIRef, BNode))
            node = NodeShape.parse(graph, ns)
            if node is not None:
                self.nodes.append(node)

        for ns in self.graph.objects(predicate=rdflib.SH.property):
            assert isinstance(ns, (URIRef, BNode))
            node = PropertyShape.parse(graph, ns)
            if node is not None:
                self.nodes.append(node)

    def dependencies(self, node: Union[URIRef, BNode], recursive=True) -> List[Union[URIRef, BNode]]:
        return self[node].dependencies(self.graph, recursive=recursive)

    def dependents(self, node: Union[URIRef, BNode], recursive=True) -> List[Union[URIRef, BNode]]:
        found = set()
        for other in self.nodes:
            if other._name == node:
                continue
            if node in other.dependencies(self.graph, recursive=recursive):
                found.add(other._name)
        return list(found)

    def __getitem__(self, key: Union[URIRef, BNode]) -> "SHACLNode":
        for node in self.nodes:
            if node._name == key:
                return node
        raise KeyError(key)


class SHACLNode:
    _name: Union[URIRef, BNode]

    @property
    def name(self) -> str:
        if hasattr(self, "_name") and isinstance(self._name, URIRef):
            return self._name.n3()
        return ""

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode, Literal]) -> "SHACLNode":
        raise NotImplementedError

    def dump(self, _: int) -> None:
        raise NotImplementedError

    # TODO: some sort of traversal method?
    # what are some optimizations we can try?
    # how do I rewrite a subtree?

    # TODO: find redundant shapes

    def dependencies(self, graph: rdflib.Graph, recursive=True) -> List[Union[URIRef, BNode]]:
        """
        Return all shapes (node or property) that this shape depends on w/n the given graph.
        If recursive is True, then also yield all shapes that depend on shapes that depend on this shape.
        """
        found = set()
        nodes = graph.cbd(self._name).all_nodes()
        for node in nodes:
            if graph.query(f"ASK {{ {{ <{node}> a sh:NodeShape }} UNION {{ <{node}> a sh:PropertyShape }} UNION {{ ?x sh:node <{node}> }} UNION {{ ?x sh:property <{node}> }} }}"):
                assert isinstance(node, (URIRef, BNode))
                found.add(node)
        if recursive:
            stack = deque(found)
            while len(stack) > 0:
                node = stack.pop()
                if node in found:
                    continue
                found.add(node)
                stack.extend(graph.cbd(node).all_nodes())
        return list(found)


class NodeShape(SHACLNode):
    properties: List["PropertyShape"]
    target: Optional["NodeShapeTarget"]
    hasClass: Union[URIRef, BNode]
    matchesNode: Optional["NodeShape"]
    closed: bool
    or_clauses: List["OrClause"]
    not_clauses: List["NotClause"]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["NodeShape"]:
        if node is None:
            return None
        ns = NodeShape()
        ns._name = node
        ns.target = NodeShapeTarget.parse(graph, node)
        ns.hasClass = graph.value(node, SH["class"])
        ns.matchesNode = NodeShape.parse(graph, graph.value(node, SH["node"]))
        ns.closed = graph.value(node, SH.closed, default=False)
        ns.or_clauses = drop_none(
            [OrClause.parse(graph, oc) for oc in graph.objects(node, SH["or"])]
        )
        ns.not_clauses = drop_none(
            [NotClause.parse(graph, nc) for nc in graph.objects(node, SH["not"])]
        )
        ns.properties = drop_none(
            [PropertyShape.parse(graph, ps) for ps in graph.objects(node, SH.property)]
        )
        return ns

    def dump(self, indent=0):
        print(f"{'  '*indent}NodeShape {self.name}:")
        if self.target is not None:
            print(f"{'  '*(indent+1)}target:", self.target.dump(indent=indent))
        if self.hasClass is not None:
            print(f"{'  '*(indent+1)}hasClass:", self.hasClass)
        if self.matchesNode is not None:
            self.matchesNode.dump(indent=indent + 1)
        print(f"{'  '*(indent+1)}closed:", self.closed)
        for oc in self.or_clauses:
            oc.dump(indent=indent + 1)
        for nc in self.not_clauses:
            nc.dump(indent=indent + 1)
        for ps in self.properties:
            ps.dump(indent=indent + 1)


class OrClause(SHACLNode):
    node_shapes: List[NodeShape]

    @classmethod
    def parse(
        cls, graph: rdflib.Graph, node: Union[URIRef, BNode]
    ) -> Optional["OrClause"]:
        if node is None:
            return None
        oc = OrClause()
        oc._name = node
        shapes = Collection(graph, node)
        oc.node_shapes = drop_none([NodeShape.parse(graph, s) for s in shapes])
        return oc

    def dump(self, indent=0):
        print(f"{'  '*indent}OrClause {self.name}:")
        for ns in self.node_shapes:
            ns.dump(indent=indent + 1)



class NotClause(SHACLNode):
    not_shape: NodeShape

    @classmethod
    def parse(
        cls, graph: rdflib.Graph, node: Union[URIRef, BNode]
    ) -> Optional["NotClause"]:
        if node is None:
            return None
        nc = NotClause()
        nc._name = node
        not_shape = NodeShape.parse(graph, node)
        assert not_shape is not None
        nc.not_shape = not_shape
        return nc

    def dump(self, indent=0):
        print(f"{'  '*indent}NotClause {self.name}:")
        self.not_shape.dump(indent=indent + 1)


class Path(SHACLNode):
    predicatePath: Optional[URIRef]
    sequencePath: List["Path"]
    alternativePath: List["Path"]
    inversePath: Optional["Path"]
    zeroOrOnePath: Optional["Path"]
    oneOrMorePath: Optional["Path"]
    zeroOrMorePath: Optional["Path"]

    def __init__(self):
        self.predicatePath = None
        self.sequencePath = []
        self.alternativePath = []
        self.inversePath = None
        self.zeroOrOnePath = None
        self.oneOrMorePath = None
        self.zeroOrMorePath = None

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["Path"]:
        if node is None:
            return None
        p = Path()
        p._name = node
        path = node
        pathlist = Collection(graph, path)
        if graph.value(path, SH.inversePath):
            p.inversePath = Path.parse(graph, graph.value(path, SH.inversePath))
        elif graph.value(path, SH.zeroOrOnePath):
            p.zeroOrOnePath = Path.parse(graph, graph.value(path, SH.zeroOrOnePath))
        elif graph.value(path, SH.oneOrMorePath):
            p.oneOrMorePath = Path.parse(graph, graph.value(path, SH.oneOrMorePath))
        elif graph.value(path, SH.zeroOrMorePath):
            p.zeroOrMorePath = Path.parse(graph, graph.value(path, SH.zeroOrMorePath))
        elif len(pathlist) > 0:
            p.sequencePath = drop_none([Path.parse(graph, p) for p in pathlist])
        elif graph.value(path, SH.alternativePath):
            p.alternativePath = graph.value(path, SH.alternativePath)
        else:
            assert isinstance(node, URIRef)
            p.predicatePath = node
        return p

    def rollup(self) -> str:
        if self.predicatePath is not None:
            return self.predicatePath
        elif self.sequencePath:
            return "/".join([p.rollup() for p in self.sequencePath])
        elif self.alternativePath:
            return "|".join([p.rollup() for p in self.alternativePath])
        elif self.inversePath:
            return self.inversePath.rollup() + "^"
        elif self.zeroOrOnePath:
            return self.zeroOrOnePath.rollup() + "?"
        elif self.oneOrMorePath:
            return self.oneOrMorePath.rollup() + "+"
        elif self.zeroOrMorePath:
            return self.zeroOrMorePath.rollup() + "*"
        else:
            return ""

    def dump(self, indent=0):
        print(f"{'  '*indent}Path: {self.rollup()}")


class PropertyShape(SHACLNode):
    path: Path
    minCount: int
    maxCount: int
    hasValue: Union[URIRef, Literal]
    hasClass: Union[URIRef, BNode]
    hasDatatype: Union[URIRef, BNode]
    hasNodeKind: Union[URIRef, BNode]
    matchesNode: Optional[NodeShape]
    matchesProperty: Optional["PropertyShape"]
    qualifiedValueShape: Optional["QualifiedValueShape"]

    @classmethod
    def parse(
        cls, graph: rdflib.Graph, node: Union[URIRef, BNode]
    ) -> Optional["PropertyShape"]:
        if node is None:
            return None
        ps = PropertyShape()
        ps._name = node

        path = Path.parse(graph, graph.value(node, SH.path))
        assert path is not None
        ps.path = path

        ps.minCount = graph.value(node, SH.minCount)
        ps.maxCount = graph.value(node, SH.maxCount)
        ps.hasValue = graph.value(node, SH.hasValue)
        ps.hasClass = graph.value(node, SH["class"])
        ps.hasDatatype = graph.value(node, SH["datatype"])
        ps.hasNodeKind = graph.value(node, SH["nodeKind"])
        ps.matchesNode = NodeShape.parse(graph, graph.value(node, SH["node"]))
        ps.qualifiedValueShape = QualifiedValueShape.parse(
            graph, graph.value(node, SH.qualifiedValueShape)
        )
        if ps.qualifiedValueShape is not None:
            ps.qualifiedValueShape.qualifiedMinCount = graph.value(
                node, SH.qualifiedMinCount
            )
            ps.qualifiedValueShape.qualifiedMaxCount = graph.value(
                node, SH.qualifiedMaxCount
            )
        return ps

    def dump(self, indent=0):
        print(f"{'  '*indent}PropertyShape {self.name}:")
        if self.path is not None:
            self.path.dump(indent=indent + 1)
        if self.minCount is not None:
            print(f"{'  '*(indent+1)}minCount:", self.minCount)
        if self.maxCount is not None:
            print(f"{'  '*(indent+1)}maxCount:", self.maxCount)
        if self.hasValue is not None:
            print(f"{'  '*(indent+1)}hasValue:", self.hasValue)
        if self.hasClass is not None:
            print(f"{'  '*(indent+1)}hasClass:", self.hasClass)
        if self.hasDatatype is not None:
            print(f"{'  '*(indent+1)}hasDatatype:", self.hasDatatype)
        if self.hasNodeKind is not None:
            print(f"{'  '*(indent+1)}hasNodeKind:", self.hasNodeKind)
        if self.matchesNode is not None:
            self.matchesNode.dump(indent=indent + 1)
        if self.qualifiedValueShape is not None:
            self.qualifiedValueShape.dump(indent=indent + 1)

class QualifiedValueShape(SHACLNode):
    qualifiedMinCount: int
    qualifiedMaxCount: int
    qualifiedValueShape: Optional[NodeShape]

    @classmethod
    def parse(
        cls, graph: rdflib.Graph, node: URIRef
    ) -> Optional["QualifiedValueShape"]:
        if node is None:
            return None
        qvs = QualifiedValueShape()
        qvs._name = node
        qvs.qualifiedValueShape = NodeShape.parse(graph, node)
        return qvs

    def dump(self, indent=0):
        print(f"{'  '*indent}QualifiedValueShape {self.name}:")
        if self.qualifiedMinCount is not None:
            print(f"{'  '*(indent+1)}qualifiedMinCount:", self.qualifiedMinCount)
        if self.qualifiedMaxCount is not None:
            print(f"{'  '*(indent+1)}qualifiedMaxCount:", self.qualifiedMaxCount)
        assert self.qualifiedValueShape is not None
        self.qualifiedValueShape.dump(indent=indent + 1)


class NodeShapeTarget(SHACLNode):
    targetClass: Union[URIRef, BNode]
    targetNode: NodeShape
    targetObjectsOf: URIRef
    targetSubjectsOf: URIRef

    @classmethod
    def parse(
        cls, graph: rdflib.Graph, node: Union[URIRef, BNode]
    ) -> Optional["NodeShapeTarget"]:
        if node is None:
            return None
        if graph.value(node, SH.targetClass):
            target = NodeShapeTarget()
            target.targetClass = graph.value(node, SH.targetClass)
            return target
        elif graph.value(node, SH.targetNode):
            target = NodeShapeTarget()
            target.targetNode = NodeShape.parse(graph, graph.value(node, SH.targetNode))
            return target
        elif graph.value(node, SH.targetObjectsOf):
            target = NodeShapeTarget()
            target.targetObjectsOf = graph.value(node, SH.targetObjectsOf)
            return target
        elif graph.value(node, SH.targetSubjectsOf):
            target = NodeShapeTarget()
            target.targetSubjectsOf = graph.value(node, SH.targetSubjectsOf)
            return target
        return None

    def dump(self, indent=0):
        print(f"{'  '*indent}NodeShapeTarget:")
        if self.targetClass:
            print(f"{'  '*(indent+1)}targetClass:", self.targetClass)
        elif self.targetNode:
            self.targetNode.dump(indent=indent + 1)
        elif self.targetObjectsOf:
            print(f"{'  '*(indent+1)}targetObjectsOf:", self.targetObjectsOf)
        elif self.targetSubjectsOf:
            print(f"{'  '*(indent+1)}targetSubjectsOf:", self.targetSubjectsOf)


def parse(graph: rdflib.Graph, node: Union[URIRef, BNode]) -> NodeShape:
    return NodeShape.parse(graph, node)


if __name__ == "__main__":
    graph = rdflib.Graph()
    graph.parse("ASHRAE/G36/4.1-vav-cooling-only/brick-shapes.ttl", format="turtle")
    pyshacl.validate(graph, advanced=True, inference='rdfs', abort_on_first=False, allow_warnings=True, js=True)

    node = parse(graph, G36["vav-cooling-only"])
    node.dump()

    # node = parse(graph, G36["zone-with-temp-sensor"])
    # node.dump()

    # ps = PropertyShape.parse(graph, G36["window-switch"])
    # ps.dump()

    ps = PropertyShape.parse(graph, G36["zone-temperature2"])
    ps.dump()

    sg = ShapeGraph(graph)
    print(sg.nodes)
    zt = sg[G36["zone-temperature2"]]
    print(zt)
    print('dependencies')
    for c in sg.dependencies(G36["zone-temperature2"]):
        print(c)
    print('dependents')
    for c in sg.dependents(G36["zone-temperature2"]):
        print(c)
