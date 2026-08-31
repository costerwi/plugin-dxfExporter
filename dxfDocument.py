#!/usr/bin/env python3
"""Classes for working with DXF file entities

Carl Osterwisch, July 2026
"""

import sys
from time import perf_counter
import numpy as np

def threeD(point):
    """Append 0.0 until point is 3D

    >>> threeD([1., 2.])
    [1.0, 2.0, 0.0]
    """

    coord = list(point[:3])
    while len(coord) < 3:
        coord.append(0.0)
    return coord

class Entity(list):
    """Members and methods common to all DXF entities"""
    def __init__(self, doc):
        super().__init__()
        if doc is not None:
            self.handle = doc.newHandle(self)  # unique in this document

    @classmethod
    def print(cls, *records, file):
        """Print formatted dxf records to specified file

        >>> e = Entity(None)
        >>> e.print(0, "TEST", 100, "SOMETHING", file=sys.stdout)
          0
        TEST
        100
        SOMETHING
        """

        assert len(records)%2 == 0, "Even number of arguments required"
        for group, value in zip(records[::2], records[1::2]):
            print("{:3d}\n{}".format(group, value), file=file)

    def export(self, owner, file):
        self.print(
            0, self.name,
            #5, "{:X}".format(self.handle),
            file=file)
        if owner is not None:
            #self.print(330, "{:X}".format(owner.handle), file=file)
            pass
        self.print(
            8, 0,  # layer 0
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
        center = threeD(self.center)
        self.print(
            10, center[0],
            20, center[1],
            30, center[2],
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
        point1 = threeD(self.point1)
        point2 = threeD(self.point2)
        self.print(
            10, point1[0],
            20, point1[1],
            30, point1[2],
            11, point2[0],
            21, point2[1],
            31, point2[2],
            file=file)

class Polyline(Entity):
    """Multiple vertices connected by lines"""
    name = "POLYLINE"
    def __init__(self, doc, closed=0):
        super().__init__(doc)
        if closed:
            self.closed = 1
        else:
            self.closed = 0
        self.seqend = Seqend(doc)

    def export(self, owner, file):
        super().export(owner, file)
        self.print(
            66, 1,  # flag: entities follow
            70, self.closed,  # 1=closed, 128=continuous linetype
            file=file)
        for vertex in self:
            vertex.export(self, file)
        self.seqend.export(self, file)

class Seqend(Entity):
    """End of sequence"""
    name = "SEQEND"

class Vertex(Entity):
    """A geometric point

    >>> doc = Document()
    >>> v = Vertex(doc, [1.,4.], angle=180)
    >>> v.export(None, file=sys.stdout)
      0
    VERTEX
      8
    0
     10
    1.0
     20
    4.0
     30
    0.0
     42
    0.9999999999999999
    """

    name = "VERTEX"
    def __init__(self, doc, pos, angle=0):
        super().__init__(doc)
        self.pos = pos
        self.angle = angle

    def __bool__(self):
        return True  # otherwise based on len(self) which is always False

    def export(self, owner, file):
        super().export(owner, file)
        pos = threeD(self.pos)
        self.print(
            10, pos[0],
            20, pos[1],
            30, pos[2],
            file=file)
        if self.angle != 0:
            bulge = np.tan(np.radians(self.angle/4))  # 0=straight segment, 1=semicircle, <0=clockwise
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

    def freeEdges(self, doc):
        """Return list of Polyline(s) of mesh free edges"""
        edges = {}
        def addEdge(n1, n2):
            if n1 < n2:
                edge = n1, n2
            else:
                edge = n2, n1
            existing = edges.get(edge)
            if existing is None:
                edges[edge] = True  # first element to reference this edge
            elif existing is True:
                edges[edge] = False  # duplicate found
        for face in self[len(self.nodemap):]:
            assert isinstance(face, PolyfaceElement)
            N = len(face.nodes)
            if N == 3:
                n1, n2, n3 = face.nodes
                addEdge(n1, n2)
                addEdge(n1, n3)
                addEdge(n2, n3)
            elif N == 4:
                n1, n2, n3, n4 = face.nodes
                addEdge(n1, n2)
                addEdge(n2, n3)
                addEdge(n3, n4)
                addEdge(n4, n1)
        edges = {k for k, v in edges.items() if v}  # set of free edges

        polylines = []
        while edges:
            nextEdge = edges.pop()  # start anywhere
            connectedNodes = list(nextEdge)
            while nextEdge:
                end = connectedNodes[-1]
                for nextEdge in edges:  # TODO how bad is this performance?
                    if end == nextEdge[0]:
                        connectedNodes.append(nextEdge[1])
                        break
                    elif end == nextEdge[1]:
                        connectedNodes.append(nextEdge[0])
                        break
                else:
                    nextEdge = None  # not matched
                edges.discard(nextEdge)

            polyline = Polyline(doc, closed = True)
            polylines.append(polyline)
            for nid in connectedNodes:
                polyfaceNode = self[self.nodemap[nid] - 1]  # dxf node indices start from 1
                polyline.append(Vertex(doc, polyfaceNode.pos))
        return polylines

    def is2D(self):
        """Return True if all nodes are on the XY plane"""
        return all(len(n.pos < 3) or abs(n.pos[2]) < 1e-7 for n in self[:len(self.nodemap)])

    def freeFaces(self, doc):
        """Return PolyfaceMesh with duplicate (interior) faces removed"""
        if self.is2D():
            return self  # skip for 2D
        faces = {}
        for face in self[len(self.nodemap):]:
            assert isinstance(face, PolyfaceElement)
            faceNodes = tuple(sorted(face.nodes))
            existing = faces.get(faceNodes)
            if existing is None:
                faces[faceNodes] = face  # first face with these nodes
            elif existing:
                faces[faceNodes] = False  # duplicate found
        faces = {k: v for k, v in faces.items() if v}  # dict of free faces
        newMesh = PolyfaceMesh(doc)
        for faceNodes in faces:
            for nid in faceNodes:
                if not nid in newMesh.nodemap:
                    node = self[self.nodemap[nid] - 1]  # dxf node indices start from 1
                    newMesh.appendNode(node, label=nid)  # uses the same PolymeshNode
        newMesh.extend(faces.values())  # uses the same PolymeshElements
        return newMesh

    def splitFeatures(self, doc, angle=20):
        """Return list of PolyfaceMesh split by feature angle"""
        if self.is2D():
            return [self]  # skip for 2D
        unmatched = [e for e in self[len(self.nodemap):]]
        v0 = []
        v1 = []
        unmatchedNodes = []
        for face in unmatched:
            points = np.array([self[self.nodemap[nid] - 1].pos for nid in face.nodes])
            v0.append( points[1] - points[0] )  # vector to first point
            v1.append( points[-1] - points[0] )  # vector to last point
            faceNodes = list(face.nodes)
            while len(faceNodes) < 4:
                faceNodes.append(-1)  # dummy node id so all rows will have 4 columns
            unmatchedNodes.append(faceNodes)
        unmatchedNormals = np.cross(v0, v1)  # arbitary vector length
        unmatchedNormals /= np.linalg.norm(unmatchedNormals, axis=1, keepdims=True)
        unmatchedNodes = np.array(unmatchedNodes)
        del v0, v1

        dotCriteria = np.cos(np.radians(angle))
        features = []  # list of new PolyfaceMesh
        while unmatched:
            fringeFace = unmatched.pop(0)  # start anywhere
            matched = [fringeFace]
            unmatchedNodes = unmatchedNodes[1:]
            uniqueNodes = set(fringeFace.nodes)
            fringeFace.normal, unmatchedNormals = unmatchedNormals[0], unmatchedNormals[1:]
            i = 0
            while i < len(matched):
                fringeFace = matched[i]
                i += 1
                touching = np.zeros(len(unmatched), dtype=bool)
                for nid in fringeFace.nodes:
                    np.logical_or(touching, np.any(nid == unmatchedNodes, axis=1), out=touching)
                if not np.any(touching):
                    continue
                tangent = np.zeros_like(touching, dtype=bool)
                tangent[touching] = unmatchedNormals[touching].dot(fringeFace.normal) >= dotCriteria  # true if normals are close
                np.logical_and(touching, tangent, out=tangent)  # true if touching and normals are close
                indices = np.flatnonzero(tangent).tolist()
                if not indices:
                    continue
                newlyAdded = [unmatched.pop(i) for i in reversed(indices)]
                newlyAdded.reverse()  # un-reverse the sequence
                for face, normal in zip(newlyAdded, unmatchedNormals[tangent]):
                    face.normal = normal
                matched.extend(newlyAdded)
                uniqueNodes.update(unmatchedNodes[tangent].flat)
                unmatchedNodes = unmatchedNodes[~tangent]
                unmatchedNormals = unmatchedNormals[~tangent]
            newMesh = PolyfaceMesh(doc)
            features.append(newMesh)
            uniqueNodes.discard(-1)
            for nid in sorted(uniqueNodes):
                node = self[self.nodemap[nid] - 1]  # dxf node indices start from 1
                newMesh.appendNode(node, label=nid)  # uses the same PolymeshNode
            newMesh.extend(matched)  # uses the same PolymeshElements
        return features

    def export(self, owner, file):
        m = len(self.nodemap)  # number of nodes
        n = len(self) - m  # number of elements
        if m*n == 0:
            return  # don't export empty mesh
        # TODO split into multiple PolyfaceMesh if size limits become a problem
        super().export(owner, file)
        self.print(
            66, 1,  # flag: entities follow
            70, 64,  # 64=polyface mesh type
            file=file)
        self.print(
            71, m,
            72, n,
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
        super().__init__(doc, [])  # coordinates are not used
        self.nodes = tuple(nodes[:4])  # node labels

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
        values.append(value)
    return values

def getRecords(file):
    """Split DXF file into dicts of related records

    >>> with open("example.dxf") as dxf:
    ...     e = list(getRecords(dxf))
    >>> e[0]
    {0: 'SECTION', 2: 'ENTITIES'}
    """

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
    """Create a DXF document by importing an existing DXF file

    >>> with open("example.dxf") as dxf:
    ...     doc = fromFile(dxf)
    >>> len(doc.allEntities)
    78
    >>> len(doc[0])  # entities in first section
    11
    >>> with open("exported.dxf", "w") as dxf:
    ...     doc.export(file=dxf)
    """

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
            radius = float(records.get(40, 0.0))
            section.append(Circle(doc, center, radius))
        elif name == "ARC":
            center = find(records, [10, 20, 30], 0.0)
            radius, startAngle, endAngle = find(records, [40, 50, 51], 0.0)
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
                container = Polyline(doc, closed=kind & 1)
                section.append(container)
        elif name == "VERTEX":
            pos = find(records, [10, 20, 30], 0.0)
            buldge = float(records.get(42, 0.0))
            angle = np.degrees(np.atan(buldge)*4)
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

if __name__ == "__main__":
    import doctest
    doctest.testmod()
