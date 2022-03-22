import brickschema

g = brickschema.Graph()
g.load_file("/home/gabe/src/Brick/Brick/Brick.ttl")
g.load_file("brick.ttl")
g.load_file("example.ttl")
valid, _, report = g.validate()
assert valid, report
