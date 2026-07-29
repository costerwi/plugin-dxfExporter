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
        for block in fieldU.bulkDataBlocks:
            instance = block.instance
            try:
                nodeLabels = set(activeNodes[instance.name])
                elementLabels = set(activeElements[instance.name])
            except KeyError:
                continue
            assert len(instance.nodes) == len(block.data)
            mesh = dxf.PolyfaceMesh(doc)
            section.append(mesh)
            data = np.asarray(block.data)
            if data.shape[1] == 2:
                data = np.c_[data, np.zeros(len(data))]  # extend to 3D
            for node, disp in zip(instance.nodes, scaleFactor*data):
                if node.label not in nodeLabels:
                    continue
                coord = disp + node.coordinates  # TODO check performance
                mesh.appendNode(dxf.PolyfaceNode(doc, coord), node.label)
            for element in instance.elements:
                if element.label not in elementLabels:
                    continue
                # TODO faces of other element types
                mesh.append(dxf.PolyfaceElement(doc, element.connectivity))
    else:
        # Undeformed
        for instName, nodeLabels in activeNodes.items():
            try:
                elementLabels = activeElements[instName]
                instance = odb.rootAssembly.instances[instName]
            except KeyError:
                continue
            mesh = dxf.PolyfaceMesh(doc)
            section.append(mesh)
            for node in instance.nodes:
                if node.label not in nodeLabels:
                    continue
                mesh.appendNode(dxf.PolyfaceNode(doc, node.coordinates), node.label)
            for element in instance.elements:
                if element.label not in elementLabels:
                    continue
                # TODO faces of other element types
                mesh.append(dxf.PolyfaceElement(doc, element.connectivity))
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
