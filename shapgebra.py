import rdflib
from rdflib.collection import Collection
from rdflib import URIRef, BNode, Literal, Namespace
from typing import List, Union, Optional, Any

SH = Namespace("http://www.w3.org/ns/shacl#")
G36 = Namespace("urn:ashrae/g36/4.1/vav-cooling-only/")


def drop_none(l: List[Optional[Any]]) -> List[Any]:
    return [x for x in l if x is not None]


class NodeShape:
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
        ns.target = NodeShapeTarget.parse(graph, node)
        ns.closed = graph.value(node, SH.closed, default=False)
        ns.or_clauses = drop_none([OrClause.parse(graph, oc) for oc in graph.objects(node, SH["or"])])
        ns.not_clauses = drop_none([NotClause.parse(graph, nc) for nc in graph.objects(node, SH["not"])])
        ns.properties = drop_none([PropertyShape.parse(graph, ps) for ps in graph.objects(node, SH.property)])
        return ns

    def dump(self, indent=0):
        print(f"{'  '*indent}NodeShape:")
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
    node_shapes: List[NodeShape]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["OrClause"]:
        if node is None:
            return None
        oc = OrClause()
        shapes = Collection(graph, node)
        oc.node_shapes = [NodeShape.parse(graph, s) for s in shapes]
        return oc

    def dump(self, indent=0):
        print(f"{'  '*indent}OrClause:")
        for ns in self.node_shapes:
            ns.dump(indent=indent+1)


class NotClause:
    not_shape: NodeShape

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: Union[URIRef, BNode]) -> Optional["NotClause"]:
        if node is None:
            return None
        nc = NotClause()
        nc.not_shape = NodeShape.parse(graph, node)
        return nc

    def dump(self, indent=0):
        print(f"{'  '*indent}NotClause:")
        self.not_shape.dump(indent=indent+1)


class Path:
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
        elif pathlist is not None:
            p.sequencePath = drop_none([Path.parse(graph, p) for p in pathlist])
        elif graph.value(path, SH.alternativePath):
            p.alternativePath = graph.value(path, SH.alternativePath)
        else:
            p.predicatePath = path
        return p

    def dump(self, indent=0):
        print(f"{'  '*indent}Path:")
        if self.predicatePath is not None:
            print(f"{'  '*(indent+1)}predicatePath:", self.predicatePath)
        if self.sequencePath:
            print(f"{'  '*(indent+1)}sequencePath:")
            for p in self.sequencePath:
                p.dump(indent=indent+2)
        if self.alternativePath:
            print(f"{'  '*(indent+1)}alternativePath:")
            for ap in self.alternativePath:
                ap.dump(indent=indent+2)
        if self.inversePath is not None:
            print(f"{'  '*(indent+1)}inversePath:", self.inversePath.dump(indent+1))
        if self.zeroOrOnePath is not None:
            print(f"{'  '*(indent+1)}zeroOrOnePath:", self.zeroOrOnePath.dump(indent+1))
        if self.oneOrMorePath is not None:
            print(f"{'  '*(indent+1)}oneOrMorePath:", self.oneOrMorePath.dump(indent+1))
        if self.zeroOrMorePath is not None:
            print(f"{'  '*(indent+1)}zeroOrMorePath:", self.zeroOrMorePath.dump(indent+1))

class PropertyShape:
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
        print(f"{'  '*indent}PropertyShape:")
        if self.path is not None:
            print(f"{'  '*(indent+1)}path:", self.path.dump(indent=indent+1))
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
            print(f"{'  '*(indent+1)}matchesNode:", self.matchesNode.dump(indent=indent+1))
        if self.qualifiedValueShape is not None:
            print(f"{'  '*(indent+1)}qualifiedValueShape:", self.qualifiedValueShape.dump(indent=indent+1))


class QualifiedValueShape:
    qualifiedMinCount: int
    qualifiedMaxCount: int
    qualifiedValueShape: Optional[PropertyShape]

    @classmethod
    def parse(cls, graph: rdflib.Graph, node: URIRef) -> Optional["QualifiedValueShape"]:
        if node is None:
            return None
        qvs = QualifiedValueShape()
        qvs.qualifiedValueShape = PropertyShape.parse(graph, node)
        return qvs

    def dump(self, indent=0):
        print(f"{'  '*indent}QualifiedValueShape:")
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

    node = parse(graph, G36["vav-cooling-only"])
    node.dump()
