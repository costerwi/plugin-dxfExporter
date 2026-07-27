#!/usr/bin/env python3
"""Classes for working with DXF file entities

Carl Osterwisch, July 2026
"""

from math import pi, tan, atan
import sys
import numpy as np

class Entity(list):
    """Members and methods common to all DXF entities"""
    def __init__(self, doc):
        super().__init__()
        if doc is not None:
            self.handle = doc.newHandle(self)  # unique in this document

    @classmethod
    def print(cls, *records, file):
        """Print dxf records to specified file"""
        assert len(records)%2 == 0, "Even number of arguments required"
        for group, value in zip(records[::2], records[1::2]):
            print("{: 3d}\n{}".format(group, value), file=file)

    def export(self, owner, file):
        self.print(
            0, self.name,
            5, "{:X}".format(self.handle),
            file=file)
        if owner is not None:
            self.print(330, "{:X}".format(owner.handle), file=file)
        self.print(
            100, "AcDbEntity",
            8, 0,  # layer
            file=file)

class Document(Entity):
    """A collection of DXF sections"""
    def __init__(self, source=None):
        super().__init__(None)
        self.allEntities = []

    def newHandle(self, child):
        """Generate a unique handle for the provided child"""
        self.allEntities.append(child)
        return len(self.allEntities)  # starting from 1

    def export(self, owner=None, file=sys.stdout):
        for section in self:
            section.export(owner, file=file)
        self.print(0, "EOF", file=file)

class Section(Entity):
    """A main section of the DXF"""
    name = "SECTION"
    def __init__(self, doc, sectionName="ENTITIES"):
        super().__init__(doc)
        self.sectionName = sectionName

    def export(self, owner, file):
        self.print(
            0, self.name,
            2, self.sectionName,
            file=file)
        for child in self:
            child.export(owner, file)
        self.print(0, "ENDSEC", file=file)

class Circle(Entity):
    """A full circle"""
    name = "CIRCLE"
    def __init__(self, doc, center, radius):
        super().__init__(doc)
        self.center = center
        self.radius = radius

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDbCircle",
            10, self.center[0],
            20, self.center[1],
            30, 0,
            40, self.radius,
            file=file)

class Arc(Circle):
    """An incomplete circle"""
    name = "ARC"
    def __init__(self, doc, center, radius, startAngle, endAngle):
        super().__init__(doc, center, radius)
        self.startAngle = startAngle
        self.endAngle = endAngle

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDbArc",
            50, self.startAngle,
            51, self.endAngle,
            file=file)

class Line(Entity):
    """Straight line between two points"""
    name = "LINE"
    def __init__(self, doc, point1, point2):
        super().__init__(doc)
        self.point1 = point1
        self.point2 = point2

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDbLine",
            10, point1[0],
            20, point1[1],
            30, 0,
            11, point2[0],
            21, point2[1],
            31, 0,
            file=file)

class Polyline(Entity):
    """Multiple vertices connected by lines"""
    name = "POLYLINE"
    def __init__(self, doc):
        super().__init__(doc)
        self.seqend = Seqend(doc)

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDb2dPolyline",
            10, 0,
            20, 0,
            30, 0,
            70, 1 + 128, # 1=closed, 128=continuous linetype
            file=file)
        for vertex in self:
            vertex.export(self, file)
        self.seqend.export(self, file)

class Seqend(Entity):
    """End of sequence"""
    name = "SEQEND"

class Vertex(Entity):
    """A geometric point"""
    name = "VERTEX"
    def __init__(self, doc, pos, angle=0):
        super().__init__(doc)
        self.pos = pos
        self.angle = angle

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDbVertex",
            100, "AcDb2dVertex",
            10, self.pos[0],
            20, self.pos[1],
            30, 0,
            file=file)
            if self.angle != 0:
                bulge = tan(pi/180*angle/4)  # 0=straight segment, 1=semicircle, <0=clockwise
                self.print(42, bulge, file=file)

class PolyfaceMesh(Entity):
    """Container of PolyfaceNode and PolyfaceElement"""
    name = "POLYLINE"
    def __init__(self, doc):
        super().__init__(doc)
        self.seqend = Seqend(doc)
        self.nodemap = {}

    def appendNode(self, node, label=None):
        """Append node and add its label to the nodemap"""
        self.append(node)
        n = len(self.nodemap) + 1
        self.nodemap[label or n] = n  # map label to index

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            100, "AcDb2dPolyline",
            10, 0,
            20, 0,
            30, 0,
            70, 64,  # 64=polyface mesh type
            file=file)
        n = len(self.nodemap)
        self.print(
            71, n,  # number of nodes
            72, len(self.children) - n,  # number of elements
            file=file)
        for child in self:
            child.export(self, file)
        self.seqend.export(self, file)

class PolyfaceNode(Vertex):
    """A geometric point"""
    def export(self, owner, file):
        super().export(owner, file)
        self.print(70, 128 + 64, file=file)  # 128=polyface, 64=vertex type

class PolyfaceElement(Vertex):
    """Container of PolyfaceNode to define an element face"""
    def __init__(self, doc, nodes):
        super().__init__(doc, [0, 0])  # coordinates are not used
        self.nodes = nodes[:4]  # list of node labels

    def export(self, owner, file):
        super().export(owner, file)
        self.print(70, 128, file=file)  # 128=Polyface mesh element type
        for group, node in enumerate(self.nodes, start=71):
            self.print(group, owner.nodemap[node], file=file)

def find(records, needles, default=None):
    """Return a list of the requested values found in records"""
    values = []
    for needle in needles:
        value = records.get(needle, default)
        if isinstance(default, float):
            value = float(value)
        elif isinstance(default, int):
            value = int(value)
        values.push(value)
    return values

def getRecords(file):
    """Split DXF file into dicts of related records"""
    records = {}
    for n, line in enumerate(file):
        if n%2 == 0:
            group = int(line)
            if group == 0 and len(records):
                yield records
                records = {}
        else:
            records.setdefault(group, line.rstrip())
    yield records

def fromFile(file):
    """Create a DXF document by importing an existing DXF file"""
    doc = Document()
    section = None
    unsupported = {"ENDSEC", "EOF", "SEQEND"}
    container = []
    for records in getRecords(file):
        name = records[0]
        if name == "SECTION":
            sectionName = records.get(2, 'unknown')
            if sectionName == "ENTITIES":
                section = Section(doc, sectionName)
                doc.append(section)
            else:
                print("Section", sectionName, "is not yet supported.")
                section = None  # ignore other sections
        elif section is None:
            continue
        elif name == "CIRCLE":
            center = find(records, [10, 20, 30], 0.0)
            redius = float(records.get(40, 0.0))
            section.append(Circle(doc, center, radius))
        elif name == "ARC":
            center = find(records, [10, 20, 30], 0.0)
            redius, startAngle, endAngle = find(records, [40, 50, 51], 0.0)
            section.append(Arc(doc, center, radius, startAngle, endAngle))
        elif name == "LINE":
            point1 = find(records, [10, 20, 30], 0.0)
            point2 = find(records, [11, 21, 31], 0.0)
            section.append(Line(doc, point1, point2))
        elif name == "POLYLINE":
            kind = int(records.get(70, 0))
            if kind & 64:
                # polyface mesh
                container = PolyfaceMesh(doc)
                section.append(container)
            else:
                container = Polyline(doc)
                section.append(container)
        elif name == "VERTEX":
            pos = find(records, [10, 20, 30], 0.0)
            buldge = float(records.get(42, 0.0))
            angle = 180/pi*atan(buldge)*4
            kind = int(records.get(70, 0))
            if kind & 128:
                # polyface mesh
                if kind & 64:
                    container.appendNode(PolyfaceNode(doc, pos, angle))
                else:
                    nodes = [n for n in find(records, [71, 72, 73, 74], 0) if n != 0]
                    container.append(PolyfaceElement(doc, nodes))
            else:
                container.append(Vertex(doc, pos, angle))
        else:
            container = []
            if name not in unsupported:
                print("Entity", name, "is not yet supported.")
                unsupported.add(name)
    return doc

def fromSketch(sketch):
    """Create a DXF document from geometry of the provided CAE sketch"""
    doc = Document()
    entities = Section(doc, "ENTITIES")
    doc.append(entities)
    unsupported = set()  # set of unsupported curve types
    for curve in sketch.geometry.values():
        if curve.type != REGULAR:
            continue  # ignore construction geometry for now
        v = curve.getVertices()
        if curve.curveType == ARC:
            center = v[2].coords
            p1 = np.asarray(v[0].coords) - center
            p2 = np.asarray(v[1].coords) - center
            radius = np.linalg.norm(p1)
            startAngle = np.rad2deg(np.arctan2(p1[1], p1[0]))
            endAngle = np.rad2deg(np.arctan2(p2[1], p2[0]))
            entities.append(Arc(doc, center, radius, startAngle, endAngle))
        elif curve.curveType == CIRCLE:
            center = v[1].coords
            p = np.asarray(v[0].coords) - center
            radius = np.linalg.norm(p)
            entities.append(Circle(doc, center, radius))
        elif curve.curveType == LINE:
            entities.append(Line(doc, v[0].coords, v[1].coords))
        elif curve.curveType not in unsupported:
            print("Curve type", curve.curveType, "is not yet supported")
            unsupported.add(curve.curveType)
    return doc

def fromOdbResult(viewport):
    """Export a mesh"""
    odb = viewport.displayedObject
    odbDisplay = viewport.odbDisplay
    elements = viewport.getActiveElementLabels()
    # TODO get deformed node coordinates
    doc = Document()
    entities = Section(doc, "ENTITIES")
    doc.append(entities)
    for instance in instances:
        mesh = PolyfaceMesh(doc)
        entities.append(mesh)
        for node in nodes:
            mesh.appendNode(PolyfaceNode(doc, node.coordinates), node.label)
        for element in elements:
            mesh.append(PolyfaceElement(doc, element.connectivity))
    return doc

def export(fileName):
    """Called by Abaqus CAE to export the currently displayed object"""
    viewport = session.viewports[session.currentViewportName]
    displayedObject = viewport.displayedObject
    doc = None
    if hasattr(displayedObject, "geometry"):  # sketch is displayed
        doc = fromSketch(displayedObject)
    elif hasattr(displayedObject, "jobData"):  # odb is displayed
        doc = fromOdbResult(viewport)
    else:
        print("Currently displaed object is not yet supported for DXF output")
    if doc is not None:
        with open(fileName, "w") as dxf:
            doc.export(file=dxf)

if __name__ == "__main__":
    # Was run from File > Run Script...
    export("example.dxf")
