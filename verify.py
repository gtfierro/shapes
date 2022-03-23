import brickschema
from rdflib import URIRef

g = brickschema.Graph()
g.load_file("/home/gabe/src/Brick/Brick/Brick.ttl")
g.load_file("shapes.ttl")
g.load_file("rules.ttl")
g.load_file("example.ttl")
valid, _, report = g.validate()
assert valid, report

results = set(g.query("SELECT * WHERE { <urn:bldg#vav1> a ?type }"))
assert((URIRef('urn:ashrae/g36/4.1/vav-cooling-only/vav-cooling-only'),) in results)
