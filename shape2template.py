import rdflib
from brickschema.namespaces import bind_prefixes
from collections import defaultdict
from rdflib.collection import Collection
from functools import cached_property
from itertools import chain
from typing import List, Tuple, Set, Optional, Union
from secrets import token_hex

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
MARK = rdflib.Namespace("urn:___mark___#")

__header__ = """
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
"""

def gensym(prefix: str) -> str:
    """
    Generate a unique identifier
    """
    return MARK[f"{prefix}_{token_hex(8)}"]


class PathSet:
    def __init__(self):
        self.sequence: List[rdflib.URIRef] = []
        self.options: Set[PathSet] = set()

    def __repr__(self):
        s = "PathSet(\n"
        for p in self.sequence:
            s += f" {p}\n"
        for o in self.options:
            s += f" {o}\n|\n"
        return s + ")"


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

    def paths(self, start) -> List[Tuple[List[str], str]]:
        if len(self.options) > 0:
            return chain.from_iterable(p.paths() for p in self.options)
        last = start
        temp = ""
        for step in self.sequence:
            temp += f"<{last}> "
            last = gensym("autogen")
            temp += f"<{step}> <{last}> .\n"
        return [([temp], last)]


class Context:
    """
    Context for a graph containing shapes
    """
    def __init__(self, graph: rdflib.Graph):
        self.g = graph
        self.templates = defaultdict(list)
        for root in self.root_shapes:
            for generated in self.generate_template(root):
                self.templates[root].append(generated)

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

    def add_template(self, name: str, template: str):
        """
        Add a template to the context
        """
        self.templates[name].append(template)

    def to_dict(self):
        res = {}
        for name, templates in self.templates.items():
            for template in templates:
                tg = rdflib.Graph()
                tg.parse(data=__header__ + template, format="turtle")
                params = [str(node) for node in tg.all_nodes() if str(node).startswith(MARK)]
                for p in params:
                    template = template.replace(f"<{p}>", f"{{{p.replace(MARK, '')}}}")
                params = [node.replace(MARK, "") for node in params]
                res[name] = {
                    "body": template,
                    "params": params
                }
        return res


    def generate_template(self, shape: rdflib.URIRef) -> List[str]:
        """
        Generate a template for a given node shape
        """
        parameters = []
        dependencies = []
        generated_shapes = [""]
        g = self.g.cbd(shape)
        # get the type or target
        param = gensym("param")
        for type_prop in [SH.targetClass, SH.targetNode, SH["class"]]:
            if type_prop in g.predicates(subject=shape):
                type_ = g.value(subject=shape, predicate=type_prop)
                generated_shapes = _add_to_list(generated_shapes, f"<{param}> rdf:type <{type_}> .\n")
                parameters.append(param)
                # handle dependencies if SH.targetNode
                if type_prop == SH.targetNode:
                    dependencies.append((param, type_))
                break
        # handle 'or's
        if SH["or"] in g.predicates(subject=shape):
            _types = self._handle_node_shape_list(shape, root=param)
            for _type in _types:
                # TODO: need 'or' these together
                generated_shapes = _cross_product(generated_shapes, self.templates[_type])
        # handle properties
        for prop_shape in g.objects(subject=shape, predicate=SH.property):
            assert isinstance(prop_shape, (rdflib.URIRef, rdflib.BNode))
            # assumes the shape parameter is the first parameter we generated
            generated_prop_shapes, prop_params = self._prop_shape_to_template(parameters[0], prop_shape)
            for prop_template in generated_prop_shapes:
                generated_shapes = _add_to_list(generated_shapes, prop_template)
            parameters.extend(prop_params)
        return generated_shapes

    def _path_to_template(self, path: rdflib.URIRef, ps: Optional[PathSet] = None) -> PathSet:
        """
        Generate a template for a path object
        """
        sg = self.g.cbd(path)
        if ps is None:
            ps = PathSet()
        if len(sg) == 0: # a single property
            return ps.then(path)
        # otherwise, interpret the path
        # list of paths
        if (path, rdflib.RDF.first, None) in sg:
            parts = Collection(sg, path)
            for part in parts:
                ps = self._path_to_template(part, ps)
            return ps

        # treat all of these the same for now
        res = sg.value(subject=path, predicate=SH.zeroOrMorePath)
        if res is not None:
            return self._path_to_template(res, ps)
        res = sg.value(subject=path, predicate=SH.oneOrMorePath)
        if res is not None:
            return self._path_to_template(res, ps)
        res = sg.value(subject=path, predicate=SH.zeroOrOnePath)
        if res is not None:
            return self._path_to_template(res, ps)
        res = sg.value(subject=path, predicate=SH.alternativePath)
        if res is not None:
            parts = Collection(sg, res)
            for part in parts:
                ps = self._path_to_template(part, ps)
            return ps
        return ps

    def _prop_shape_to_template(self, root_param: str, prop_shape: Union[rdflib.URIRef, rdflib.BNode]):
        """
        Generate a template for a given property shape
        """
        parameters = []
        generated_shapes = [""]
        pg = self.g.cbd(prop_shape)
        path = pg.value(subject=prop_shape, predicate=SH.path)
        path = self._path_to_template(path)

        # TODO: handle the 'split' if there are multiple
        path_templates = path.paths(root_param)[0]
        path, last = path_templates[0][0], path_templates[1]

        generated_shapes = _add_to_list(generated_shapes, path)
        if SH["class"] in pg.predicates(subject=prop_shape):
            type_ = pg.value(subject=prop_shape, predicate=SH["class"])
            generated_shapes = _add_to_list(generated_shapes, f"<{last}> rdf:type <{type_}> .\n")
        elif SH["qualifiedValueShape"] in pg.predicates(subject=prop_shape):
            qvs = pg.value(subject=prop_shape, predicate=SH["qualifiedValueShape"])
            type_ = pg.value(subject=qvs, predicate=SH["class"])
            if type_ is not None:
                generated_shapes = _add_to_list(generated_shapes, f"<{last}> rdf:type <{type_}> .\n")
            else:
                type_ = pg.value(subject=qvs, predicate=SH["node"])
                if type_ is not None:
                    generated_shapes = _add_to_list(generated_shapes, f"<{last}> rdf:type <{type_}> .\n")
                else:
                    # TODO: use _handle_node_shape_list (returns multiple)
                    types_ = self._handle_node_shape_list(qvs)
                    for type_ in types_:
                        generated_shapes = _add_to_list(generated_shapes, f"<{last}> rdf:type <{type_}> .\n")

        return generated_shapes, parameters

    def _handle_node_shape_list(self, shape: Union[rdflib.BNode, rdflib.URIRef], root: Optional[str] = None) -> List[str]:
        """
        Returns the list of template names for each list of alternate node shapes
        """
        lists = [Collection(self.g, or_) for or_ in self.g.objects(subject=shape, predicate=SH["or"])]
        # for each list, create a set of templates with the same name
        templates = []
        for list_ in lists:
            name = gensym("shape_list")
            templates.append(name)
            for item in list_:
                if (item, rdflib.RDF.type, SH.NodeShape) in self.g:
                    for generated in self.generate_template(item):
                        self.add_template(name, generated)
                        print(f"{name}:\n{generated}")
                elif (item, rdflib.RDF.type, SH.PropertyShape) in self.g:
                    root = gensym("prop_shape") if root is None else root
                    print("ITEM", item)
                    generated_shapes, params = self._prop_shape_to_template(root, item)
                    _ = params
                    for generated in generated_shapes:
                        self.add_template(name, generated)
                        print(f"{name}:\n{generated}")
                    pass

        return templates


def _add_to_list(list_, suffix):
    """
    Add a suffix to the end of each item in a list
    """
    return [f"{item}{suffix}" for item in list_]


def _cross_product(list_a, list_b):
    """
    Return the cross product of two lists
    """
    return [f"{a}{b}" for a in list_a for b in list_b]


if __name__ == "__main__":
    ctx = Context.from_file("ASHRAE/G36/4.1-vav-cooling-only/brick-shapes.ttl")
    print(ctx.shapes)
    print(ctx.root_shapes)
    for shape in ctx.root_shapes:
        print()
        print(shape)
        for generated in ctx.generate_template(shape):
            print(generated)
    #     for name, templist in ctx.templates.items():
    #         print('*' * 80)
    #         print(name)
    #         for template in templist:
    #             print(template)
    from pprint import pprint
    pprint(ctx.to_dict())
