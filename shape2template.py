import rdflib
from rdflib.collection import Collection
from functools import cached_property
from typing import List, Any, Set
from secrets import token_hex

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")


def gensym(prefix: str) -> str:
    """
    Generate a unique identifier
    """
    return f"{prefix}_{token_hex(8)}"


class PathSet:
    def __init__(self):
        self.sequence: List[rdflib.URIRef] = []
        self.options: Set[PathSet] = set()

    def then(self, path: rdflib.URIRef) -> "PathSet":
        """
        Add a path to the set
        """
        if len(self.options) > 0:
            ps = PathSet()
            ps.options = set([p.then(path) for p in self.options])
            return ps
        self.sequence.append(path)
        return self

    def union(self, other: "PathSet") -> "PathSet":
        """
        Combine two path sets with an OR
        """
        n = PathSet()
        n.options.add(self)
        n.options.add(other)
        return n


class Context:
    """
    Context for a graph containing shapes
    """
    def __init__(self, graph: rdflib.Graph):
        self.g = graph

    @staticmethod
    def from_file(filename: str) -> 'Context':
        """
        Create a context from a file
        :param filename:
        :return:
        """
        g = rdflib.Graph()
        g.parse(filename, format="turtle")
        return Context(g)

    @cached_property
    def shapes(self) -> List[rdflib.URIRef]:
        """
        Get all shapes from a given file.
        """
        shapes = []
        q = """SELECT ?shape WHERE {
            { ?shape a sh:NodeShape }
            UNION
            { ?shape a sh:PropertyShape }
        }"""
        for row in self.g.query(q):
            assert isinstance(row, tuple)
            assert isinstance(row[0], rdflib.URIRef)
            shapes.append(row[0])
        return shapes

    @cached_property
    def root_shapes(self) -> List[rdflib.URIRef]:
        """
        Return all shapes that are not referenced by other shapes.
        """
        root_shapes = []
        for s in self.shapes:
            dependents = [other for other in self.shapes if s in self.g.cbd(other).all_nodes()]
            # if len==1, then its the defining shape
            if len(dependents) == 1:
                root_shapes.append(s)
        return root_shapes

    def _node_shape_to_template(self, shape: rdflib.URIRef) -> str:
        """
        Generate a template for a node shape.
        Node shapes have:
        - a type of the 'target' entity
        - properties
        """
        pass

    def generate_template(self, shape: rdflib.URIRef) -> str:
        """
        Generate a template for a given shape
        """
        parameters = []
        dependencies = []
        generated_shape = ""
        g = self.g.cbd(shape)
        # get the type or target
        print(g.serialize(format="turtle"))
        for type_prop in [SH.targetClass, SH.targetNode, SH["class"]]:
            if type_prop in g.predicates(subject=shape):
                type_ = g.value(subject=shape, predicate=type_prop)
                param = gensym("param")
                generated_shape += f"{param} rdf:type {type_} .\n"
                parameters.append(param)
                # handle dependencies if SH.targetNode
                if type_prop == SH.targetNode:
                    dependencies.append((param, type_))
                break
        # handle properties
        for prop_shape in g.objects(subject=shape, predicate=SH.property):
            assert isinstance(prop_shape, rdflib.URIRef)
            # assumes the shape parameter is the first parameter we generated
            generated_prop_shape, prop_params = self._prop_shape_to_template(parameters[0], prop_shape)
            parameters.extend(prop_params)
            generated_shape += generated_prop_shape
        print(parameters)
        return generated_shape

    def _path_to_template(self, path: rdflib.URIRef) -> List[Any]:
        """
        Generate a template for a path object
        """
        sg = self.g.cbd(path)
        if len(sg) == 0: # a single property
            return [path]

        # otherwise, interpret the path

        # list of paths
        if (path, rdflib.RDF.first, None) in sg:
            parts = Collection(sg, path)
            paths = [[self._path_to_template(part)] for part in parts]
            return paths

        res = sg.value(subject=path, predicate=SH.zeroOrMorePath)
        if res is not None:
            return self._path_to_template(res)
        res = sg.value(subject=path, predicate=SH.oneOrMorePath)
        if res is not None:
            return self._path_to_template(res)
        res = sg.value(subject=path, predicate=SH.zeroOrOnePath)
        if res is not None:
            return self._path_to_template(res)
        res = sg.value(subject=path, predicate=SH.alternativePath)
        if res is not None:
            parts = Collection(sg, res)
            paths = [[self._path_to_template(part)] for part in parts]
            return paths

        return [path]

    def _prop_shape_to_template(self, root_param: str, prop_shape: rdflib.URIRef):
        """
        Generate a template for a given property shape
        """
        parameters = []
        generated_shape = ""
        pg = self.g.cbd(prop_shape)
        path = pg.value(subject=prop_shape, predicate=SH.path)
        path = self._path_to_template(path)
        # now have a sequence of paths
        if len(path) > 1:
            pass
        param = gensym("param")
        parameters.append(param)
        generated_shape += f"{root_param} {path} {param} .\n"
        if SH["class"] in pg.predicates(subject=prop_shape):
            type_ = pg.value(subject=prop_shape, predicate=SH["class"])
            generated_shape += f"{param} rdf:type {type_} .\n"
        elif SH["qualifiedValueShape"] in pg.predicates(subject=prop_shape):
            qvs = pg.value(subject=prop_shape, predicate=SH["qualifiedValueShape"])
            type_ = pg.value(subject=qvs, predicate=SH["class"])
            if type_ is None:
                type_ = pg.value(subject=qvs, predicate=SH["node"])
            generated_shape += f"{param} rdf:type {type_} .\n"
        return generated_shape, parameters


if __name__ == "__main__":
    ctx = Context.from_file("ASHRAE/G36/4.1-vav-cooling-only/brick-shapes.ttl")
    print(ctx.shapes)
    print(ctx.root_shapes)
    for shape in ctx.root_shapes:
        print(shape)
        print(ctx.generate_template(shape))
