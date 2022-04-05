import rdflib
from rdflib.collection import Collection
from rdflib import URIRef, BNode, Literal, Namespace
from typing import List, Union, Optional, Any

SH = Namespace("http://www.w3.org/ns/shacl#")
G36 = Namespace("urn:ashrae/g36/4.1/vav-cooling-only/")


def drop_none(l: List[Optional[Any]]) -> List[Any]:
    return [x for x in l if x is not None]


class NodeShape:
    name: Union[URIRef, BNode]
    properties: List["PropertyShape"]
    target: Optional["NodeShapeTarget"]
    closed: bool
    or_clauses: List["OrClause"]
    not_clauses: List["NotClause"]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: URIRef) -> Optional["NodeShape"]:
        if node is None:
            return None
        ns = NodeShape()
        ns.name = node
        ns.target = NodeShapeTarget.parse(graph, node)
        ns.closed = graph.value(node, SH.closed, default=False)
        ns.or_clauses = drop_none([OrClause.parse(graph, oc) for oc in graph.objects(node, SH["or"])])
        ns.not_clauses = drop_none([NotClause.parse(graph, nc) for nc in graph.objects(node, SH["not"])])
        ns.properties = drop_none([PropertyShape.parse(graph, ps) for ps in graph.objects(node, SH.property)])
        return ns

    def dump(self, indent=0):
        print(f"{'  '*indent}NodeShape {self.name}:")
        if self.target is not None:
            print(f"{'  '*(indent+1)}target:", self.target.dump(indent=indent))
        print(f"{'  '*(indent+1)}closed:", self.closed)
        for oc in self.or_clauses:
            oc.dump(indent=indent+1)
        for nc in self.not_clauses:
            nc.dump(indent=indent+1)
        for ps in self.properties:
            ps.dump(indent=indent+1)


class OrClause:
    name: Union[URIRef, BNode]
    node_shapes: List[NodeShape]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["OrClause"]:
        if node is None:
            return None
        oc = OrClause()
        oc.name = node
        shapes = Collection(graph, node)
        oc.node_shapes = [NodeShape.parse(graph, s) for s in shapes]
        return oc

    def dump(self, indent=0):
        print(f"{'  '*indent}OrClause {self.name}:")
        for ns in self.node_shapes:
            ns.dump(indent=indent+1)


class NotClause:
    name: Union[URIRef, BNode]
    not_shape: NodeShape

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["NotClause"]:
        if node is None:
            return None
        nc = NotClause()
        nc.name = node
        nc.not_shape = NodeShape.parse(graph, node)
        return nc

    def dump(self, indent=0):
        print(f"{'  '*indent}NotClause {self.name}:")
        self.not_shape.dump(indent=indent+1)


class Path:
    name: Union[URIRef, BNode]
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
        p.name = node
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
            print('sequence!')
            p.sequencePath = drop_none([Path.parse(graph, p) for p in pathlist])
        elif graph.value(path, SH.alternativePath):
            p.alternativePath = graph.value(path, SH.alternativePath)
        else:
            p.predicatePath = node
        return p

    def rollup(self) -> str:
        if self.predicatePath is not None:
            return self.predicatePath
        elif self.sequencePath:
            return '/'.join([p.rollup() for p in self.sequencePath])
        elif self.alternativePath:
            return '|'.join([p.rollup() for p in self.alternativePath])
        elif self.inversePath:
            return self.inversePath.rollup() + '^'
        elif self.zeroOrOnePath:
            return self.zeroOrOnePath.rollup() + '?'
        elif self.oneOrMorePath:
            return self.oneOrMorePath.rollup() + '+'
        elif self.zeroOrMorePath:
            return self.zeroOrMorePath.rollup() + '*'
        else:
            return ''

    def dump(self, indent=0):
        print(f"{'  '*indent}Path: {self.rollup()}")


class PropertyShape:
    name: Union[URIRef, BNode]
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
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["PropertyShape"]:
        if node is None:
            return None
        ps = PropertyShape()
        ps.name = node
        ps.path = Path.parse(graph, graph.value(node, SH.path))
        ps.minCount = graph.value(node, SH.minCount)
        ps.maxCount = graph.value(node, SH.maxCount)
        ps.hasValue = graph.value(node, SH.hasValue)
        ps.hasClass = graph.value(node, SH["class"])
        ps.hasDatatype = graph.value(node, SH["datatype"])
        ps.hasNodeKind = graph.value(node, SH["nodeKind"])
        ps.matchesNode = NodeShape.parse(graph, graph.value(node, SH["node"]))
        ps.qualifiedValueShape = QualifiedValueShape.parse(graph, graph.value(node, SH.qualifiedValueShape))
        if ps.qualifiedValueShape is not None:
            ps.qualifiedValueShape.qualifiedMinCount = graph.value(node, SH.qualifiedMinCount)
            ps.qualifiedValueShape.qualifiedMaxCount = graph.value(node, SH.qualifiedMaxCount)
        return ps

    def dump(self, indent=0):
        print(f"{'  '*indent}PropertyShape {self.name}:")
        if self.path is not None:
            self.path.dump(indent=indent+1)
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
            self.matchesNode.dump(indent=indent+1)
        if self.qualifiedValueShape is not None:
            self.qualifiedValueShape.dump(indent=indent+1)


class QualifiedValueShape:
    name: Union[URIRef, BNode]
    qualifiedMinCount: int
    qualifiedMaxCount: int
    qualifiedValueShape: Optional[PropertyShape]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: URIRef) -> Optional["QualifiedValueShape"]:
        if node is None:
            return None
        qvs = QualifiedValueShape()
        qvs.name = node
        qvs.qualifiedValueShape = PropertyShape.parse(graph, node)
        return qvs

    def dump(self, indent=0):
        print(f"{'  '*indent}QualifiedValueShape {self.name}:")
        if self.qualifiedMinCount is not None:
            print(f"{'  '*(indent+1)}qualifiedMinCount:", self.qualifiedMinCount)
        if self.qualifiedMaxCount is not None:
            print(f"{'  '*(indent+1)}qualifiedMaxCount:", self.qualifiedMaxCount)
        self.qualifiedValueShape.dump(indent=indent+1)


class NodeShapeTarget:
    targetClass: Union[URIRef, BNode]
    targetNode: NodeShape
    targetObjectsOf: URIRef
    targetSubjectsOf: URIRef

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["NodeShapeTarget"]:
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
            self.targetNode.dump(indent=indent+1)
        elif self.targetObjectsOf:
            print(f"{'  '*(indent+1)}targetObjectsOf:", self.targetObjectsOf)
        elif self.targetSubjectsOf:
            print(f"{'  '*(indent+1)}targetSubjectsOf:", self.targetSubjectsOf)
            

def parse(graph: rdflib.Graph, node: Union[URIRef, BNode]) -> NodeShape:
    return NodeShape.parse(graph, node)


if __name__ == "__main__":
    graph = rdflib.Graph()
    graph.parse("ASHRAE/G36/4.1-vav-cooling-only/brick-shapes.ttl", format="turtle")

    # node = parse(graph, G36["vav-cooling-only"])
    # node.dump()

    # node = parse(graph, G36["zone-with-temp-sensor"])
    # node.dump()

    ps = PropertyShape.parse(graph, G36["window-switch"])
    ps.dump()
