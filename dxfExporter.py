"""Convert Abaqus CAE entities to dxfDocument for export

Carl Osterwisch, July 2026
"""

import numpy as np
from abaqus import mdb, session
from abaqusConstants import *
import dxfDocument as dxf

def fromSketch(sketch):
    """Create a DXF document from geometry of the provided CAE sketch"""
    doc = dxf.Document()
    section = dxf.Section(doc, "ENTITIES")
    doc.append(section)
    unsupported = set()  # set of unsupported curve types
    for curve in sketch.geometry.values():
        if curve.type != REGULAR:
            continue  # ignore construction geometry
        v = list(curve.getVertices())
        if curve.curveType == ARC:
            center = np.asarray(v.pop().coords)
            p1 = v.pop().coords - center
            p2 = v.pop().coords - center
            p3 = curve.pointOn - center
            if np.cross(p1, p3) < 0:
                p1, p2 = p2, p1  # must swap points for counter-clockwise convention
            radius = np.linalg.norm(p1)
            startAngle = np.rad2deg(np.arctan2(p1[1], p1[0]))
            endAngle = np.rad2deg(np.arctan2(p2[1], p2[0]))
            section.append(dxf.Arc(doc, center, radius, startAngle, endAngle))
        elif curve.curveType == CIRCLE:
            center = np.asarray(v.pop().coords)
            p = v.pop().coords - center
            radius = np.linalg.norm(p)
            section.append(dxf.Circle(doc, center, radius))
        elif curve.curveType == LINE:
            section.append(dxf.Line(doc, v.pop().coords, v.pop().coords))
        elif curve.curveType not in unsupported:
            print("Curve type {!r} is not yet supported and will be skipped".format(curve.curveType))
            unsupported.add(curve.curveType)
    return doc

def fromOdbResult(viewport):
    """Export a mesh to DXF"""
    odb = viewport.displayedObject
    odbDisplay = viewport.odbDisplay
    activeNodes = viewport.getActiveNodeLabels(useCut=True, printResults=False)
    activeElements = viewport.getActiveElementLabels(useCut=True, printResults=False)
    # TODO find edges of mesh

    doc = dxf.Document()
    section = dxf.Section(doc, "ENTITIES")
    doc.append(section)

    faceNodes = {
        4 : ( (0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2) ),
        6 : ( (0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (0, 3, 5, 2) ),
        8 : ( (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (0, 4, 7, 3) ),
        }
    faceNodes[10] = faceNodes[4]
    faceNodes[15] = faceNodes[6]
    faceNodes[20] = faceNodes[8]

    def faces(element):
        """Return a list of PolyfaceElement representing this element's faces"""
        elementFaces = []
        N = len(element.connectivity)
        if "C3D" in element.type:
            for f in faceNodes[N]:
                elementFaces.append(
                        dxf.PolyfaceElement(doc, (element.connectivity[i] for i in f))
                        )
        else:
            if N <= 4:
                elementFaces.append(dxf.PolyfaceElement(doc, element.connectivity))
            elif N == 6:
                # just the corner nodes
                elementFaces.append(dxf.PolyfaceElement(doc, element.connectivity[:3]))
            elif N == 8:
                # just the corner nodes
                elementFaces.append(dxf.PolyfaceElement(doc, element.connectivity[:4]))
        return elementFaces

    fieldU = None
    if odbDisplay.display.plotState[0] in (DEFORMED, CONTOURS_ON_DEF, SYMBOLS_ON_DEF, ORIENT_ON_DEF):
        # Gather nodal displacements
        if odbDisplay.commonOptions.deformationScaling == NONUNIFORM:
            scaleFactor = np.asarray(odbDisplay.commonOptions.nonuniformScaleFactor)
        else:
            scaleFactor = odbDisplay.commonOptions.uniformScaleFactor
        stepIndex, frameIndex = odbDisplay.fieldFrame[:2]
        step = odb.steps.values()[stepIndex]
        frame = step.frames[frameIndex]
        fieldU = frame.fieldOutputs[odbDisplay.deformedVariable[0]]

    for instanceName, nodeLabels in activeNodes.items():
        try:
            elementLabels = set(activeElements[instanceName])
        except KeyError:
            continue  # no active elements
        nodeLabels = set(nodeLabels)
        instance = odb.rootAssembly.instances[instName]
        mesh = dxf.PolyfaceMesh(doc)  # new mesh for each instance
        section.append(mesh)

        coordinates = np.array([node.coordinates for node in instance.nodes])
        if fieldU is not None:
            for block in fieldU.bulkDataBlocks:
                if block.instance != instance:
                    continue
                assert len(instance.nodes) == len(block.data)
                data = np.asarray(block.data)
                if data.shape[1] == 2:
                    # must expand 2D displacement to 3D
                    data = np.hstack([data, np.zeros([len(data),1])])
                coordinates += scaleFactor*data
                break
            else:
                pass  # no results available for this instance
        for node, coord in zip(instance.nodes, coordinates):
            if node.label in nodeLabels:
                mesh.appendNode(dxf.PolyfaceNode(doc, coord), node.label)
        for element in instance.elements:
            if element.label not in elementLabels:
                continue  # not currently displayed
            N = len(element.connectivity)
            if N >= 3:  # assumed to have faces
                mesh.extend(faces(element))
            elif N == 2:  # beam or truss
                try:
                    point1, point2 = [mesh[mesh.nodemap[nodeId]] for nodeId in element.connectivity]
                except KeyError, IndexError:
                    continue
                section.append(dxf.Line(doc, point1, point2))
    return doc

def fromXYPlot(xyPlot):
    """Create a DXF document from XYPlot curve data"""
    doc = dxf.Document()
    section = dxf.Section(doc, "ENTITIES")
    doc.append(section)
    for curveName in xyPlot.curvesToPlot:
        polyline = dxf.Polyline(doc)
        section.append(polyline)
        xyData = session.curves[curveName].data
        for xy in xyData.data:
            polyline.append(dxf.Vertex(doc, xy))
    return doc

def export(fileName):
    """Called by Abaqus CAE to export the currently displayed object"""
    viewport = session.viewports[session.currentViewportName]
    displayedObject = viewport.displayedObject
    doc = None
    if hasattr(displayedObject, "geometry"):  # sketch is displayed
        print("Exporting sketch to {!r}".format(fileName))
        doc = fromSketch(displayedObject)
    elif hasattr(displayedObject, "jobData"):  # odb is displayed
        print("Exporting mesh to {!r}".format(fileName))
        doc = fromOdbResult(viewport)
    elif hasattr(displayedObject, "curvesToPlot"):
        print("Exporting XYPlot data to {!r}".format(fileName))
        doc = fromXYPlot(displayedObject)
    elif hasattr(displayedObject, "modelName"):  # Part or Assembly
        try:
            model = mdb.models[displayedObject.modelName]
            sketch = model.sketches['__edit__']  # currently editing sketch
            print("Exporting sketch to {!r}".format(fileName))
            doc = fromSketch(sketch)
        except KeyError:
            pass
    if doc is None:
        print("The displayed {} is not yet supported for DXF export".format(displayedObject.__class__))
    else:
        with open(fileName, "w") as dxfFile:
            doc.export(file=dxfFile)
