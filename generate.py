import os
from rdflib import Namespace, URIRef
import brickschema
import brickschema.namespaces as ns

ruleGraph = brickschema.Graph()
allShapes = brickschema.Graph()
ontologies = []

RULE = Namespace("urn:rule/")
ruleGraph.add((RULE[-1], ns.RDF.type, ns.OWL.Ontology))


def find_ttl_files(path):
    """
    Find all ttl files in a directory
    """
    for root, _, files in os.walk(path):
        # skip files in topmost directory
        if root == path:
            continue
        for file in files:
            if file.endswith(".ttl"):
                print(os.path.join(root, file))
                allShapes.load_file(os.path.join(root, file))
                yield os.path.join(root, file)


for filename in find_ttl_files("."):
    g = brickschema.Graph()
    g.load_file(filename)

    ontology = next(iter(g.subjects(ns.RDF.type, ns.OWL.Ontology)))
    ontologies.append(ontology)
    ruleGraph.add((RULE[-1], ns.OWL.imports, ontology))

    # for each shape, generate a new rule where the shape is the condition
    # and the rule instantiates the target as an instance of that shape (class)
    for shape in g.subjects(predicate=ns.RDF.type, object=ns.SH.NodeShape):
        rule = RULE[str(shape).split(":")[-1]]
        ruleGraph.add((rule, ns.RDF.type, ns.SH.NodeShape))
        targetClasses = list(g.objects(subject=shape, predicate=ns.SH["class"]))
        if not targetClasses:
            continue
        ruleGraph.add((rule, ns.SH.targetClass, targetClasses[0]))
        ruleGraph.add((rule, ns.SH.rule, [
            (ns.SH.condition, shape),
            (ns.RDF.type, ns.SH.TripleRule),
            (ns.SH["subject"], ns.SH["this"]),
            (ns.SH["predicate"], ns.RDF.type),
            (ns.SH["object"], shape),
            (ns.SH["prefixes"], URIRef(ns.RDF)),
        ]))



ruleGraph.serialize("rules.ttl", format="turtle")
allShapes.serialize("shapes.ttl", format="turtle")
