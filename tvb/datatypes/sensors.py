# -*- coding: utf-8 -*-
#
#
#  TheVirtualBrain-Scientific Package. This package holds all simulators, and 
# analysers necessary to run brain-simulations. You can use it stand alone or
# in conjunction with TheVirtualBrain-Framework Package. See content of the
# documentation-folder for more details. See also http://www.thevirtualbrain.org
#
# (c) 2012-2017, Baycrest Centre for Geriatric Care ("Baycrest") and others
#
# This program is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software Foundation,
# either version 3 of the License, or (at your option) any later version.
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE.  See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with this
# program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#   CITATION:
# When using The Virtual Brain for scientific publications, please cite it as follows:
#
#   Paula Sanz Leon, Stuart A. Knock, M. Marmaduke Woodman, Lia Domide,
#   Jochen Mersmann, Anthony R. McIntosh, Viktor Jirsa (2013)
#       The Virtual Brain: a simulator of primate brain network dynamics.
#   Frontiers in Neuroinformatics (7:10. doi: 10.3389/fninf.2013.00010)
#
#

"""
The Sensors dataType. This brings together the scientific and framework 
methods that are associated with the sensor dataTypes.

.. moduleauthor:: Stuart A. Knock <stuart.knock@gmail.com>
.. moduleauthor:: Lia Domide <lia.domide@codemart.ro>
.. moduleauthor:: Marmaduke Woodman <marmaduke.woodman@univ-amu.fr>

"""

import numpy
from tvb.datatypes import arrays
from tvb.basic.logger.builder import get_logger
from tvb.basic.traits import types_basic
from tvb.basic.traits.types_mapped import MappedType
from tvb.basic.readers import FileReader, try_get_absolute_path

LOG = get_logger(__name__)

EEG_POLYMORPHIC_IDENTITY = "EEG"
MEG_POLYMORPHIC_IDENTITY = "MEG"
INTERNAL_POLYMORPHIC_IDENTITY = "Internal"


class Sensors(MappedType):
    """
    Base Sensors class.
    All sensors have locations.
    Some will have orientations, e.g. MEG.
    """

    _ui_name = "Unknown sensors"

    sensors_type = types_basic.String

    __mapper_args__ = {'polymorphic_on': 'sensors_type'}

    labels = arrays.StringArray(label="Sensor labels")

    locations = arrays.PositionArray(label="Sensor locations")

    has_orientation = types_basic.Bool(default=False)

    orientations = arrays.OrientationArray(required=False)

    number_of_sensors = types_basic.Integer(label="Number of sensors",
                                            doc="""The number of sensors described by these Sensors.""")

    # introduced to accommodate real sensors sets which have sensors
    # that should be zero during simulation i.e. ECG (heart), EOG,
    # reference gradiometers, etc.
    usable = arrays.BoolArray(required=False, label="Usable sensors",
                              doc="The sensors in set which are used for signal data.")

    @classmethod
    def from_file(cls, source_file="eeg_brainstorm_65.txt", instance=None):

        if instance is None:
            result = cls()
        else:
            result = instance

        source_full_path = try_get_absolute_path("tvb_data.sensors", source_file)
        reader = FileReader(source_full_path)

        result.labels = reader.read_array(dtype="string", use_cols=(0,))
        result.locations = reader.read_array(use_cols=(1, 2, 3))

        return result


    def configure(self):
        """
        Invoke the compute methods for computable attributes that haven't been
        set during initialization.
        """
        super(Sensors, self).configure()
        self.number_of_sensors = self.labels.shape[0]


    def _find_summary_info(self):
        """
        Gather scientifically interesting summary information from an instance
        of this datatype.
        """
        summary = {"Sensor type": self.sensors_type,
                   "Number of Sensors": self.number_of_sensors}
        return summary


    def sensors_to_surface(self, surface_to_map):
        """
        Map EEG sensors onto the head surface (skin-air).

        EEG sensor locations are typically only given on a unit sphere, that is,
        they are effectively only identified by their orientation with respect
        to a coordinate system. This method is used to map these unit vector
        sensor "locations" to a specific location on the surface of the skin.

        Assumes coordinate systems are aligned, i.e. common x,y,z and origin.

        """
        # Normalize sensor and vertex locations to unit vectors
        norm_sensors = numpy.sqrt(numpy.sum(self.locations ** 2, axis=1))
        unit_sensors = self.locations / norm_sensors[:, numpy.newaxis]
        norm_verts = numpy.sqrt(numpy.sum(surface_to_map.vertices ** 2, axis=1))
        unit_vertices = surface_to_map.vertices / norm_verts[:, numpy.newaxis]

        sensor_locations = numpy.zeros((self.number_of_sensors, 3))
        for k in range(self.number_of_sensors):
            # Find the surface vertex most closely aligned with current sensor.
            current_sensor = unit_sensors[k]
            alignment = numpy.dot(current_sensor, unit_vertices.T)
            one_ring = []

            while not one_ring:
                closest_vertex = alignment.argmax()
                # Get the set of triangles in the neighbourhood of that vertex.
                # NOTE: Intersection doesn't always fall within the 1-ring, so, all
                #      triangles contained in the 2-ring are considered.
                one_ring = surface_to_map.vertex_neighbours[closest_vertex]
                if not one_ring:
                    alignment[closest_vertex] = min(alignment)

            local_tri = [surface_to_map.vertex_triangles[v] for v in one_ring]
            local_tri = list(set([tri for subar in local_tri for tri in subar]))

            # Calculate a parametrized plane line intersection [t,u,v] for the
            # set of local triangles, which are considered as defining a plane.
            tuv = numpy.zeros((len(local_tri), 3))
            for i, tri in enumerate(local_tri):
                edge_01 = (surface_to_map.vertices[surface_to_map.triangles[tri, 0]] -
                           surface_to_map.vertices[surface_to_map.triangles[tri, 1]])
                edge_02 = (surface_to_map.vertices[surface_to_map.triangles[tri, 0]] -
                           surface_to_map.vertices[surface_to_map.triangles[tri, 2]])
                see_mat = numpy.vstack((current_sensor, edge_01, edge_02))

                tuv[i] = numpy.linalg.solve(see_mat.T, surface_to_map.vertices[surface_to_map.triangles[tri, 0].T])

            # Find  which line-plane intersection falls within its triangle
            # by imposing the condition that u, v, & u+v are contained in [0 1]
            local_triangle_index = ((0 <= tuv[:, 1]) * (tuv[:, 1] < 1) *
                                    (0 <= tuv[:, 2]) * (tuv[:, 2] < 1) *
                                    (0 <= (tuv[:, 1] + tuv[:, 2])) * ((tuv[:, 1] + tuv[:, 2]) < 2)).nonzero()[0]

            if len(local_triangle_index) == 1:
                # Scale sensor unit vector by t so that it lies on the surface.
                sensor_locations[k] = current_sensor * tuv[local_triangle_index[0], 0]

            elif len(local_triangle_index) < 1:
                # No triangle was found in proximity. Draw the sensor somehow in the surface extension area
                LOG.warning("Could not find a proper position on the given surface for sensor %d:%s. "
                            "with direction %s" % (k, self.labels[k], str(self.locations[k])))
                distances = (abs(tuv[:, 1] + tuv[:, 2]))
                local_triangle_index = distances.argmin()
                # Scale sensor unit vector by t so that it lies on the surface.
                sensor_locations[k] = current_sensor * tuv[local_triangle_index, 0]

            else:
                # More than one triangle was found in proximity. Pick the first.
                # Scale sensor unit vector by t so that it lies on the surface.
                sensor_locations[k] = current_sensor * tuv[local_triangle_index[0], 0]

        return sensor_locations


class SensorsEEG(Sensors):
    """
    EEG sensor locations are represented as unit vectors, these need to be
    combined with a head(outer-skin) surface to obtain actual sensor locations
    ::

                              position
                                 |
                                / \\
                               /   \\
        file columns: labels, x, y, z

    """
    _ui_name = "EEG Sensors"

    __tablename__ = None

    __mapper_args__ = {'polymorphic_identity': EEG_POLYMORPHIC_IDENTITY}

    sensors_type = types_basic.String(default=EEG_POLYMORPHIC_IDENTITY)

    has_orientation = types_basic.Bool(default=False, order=-1)


class SensorsMEG(Sensors):
    """
    These are actually just SQUIDS. Axial or planar gradiometers are achieved
    by calculating lead fields for two sets of sensors and then subtracting...
    ::

                              position  orientation
                                 |           |
                                / \         / \\
                               /   \       /   \\
        file columns: labels, x, y, z,   dx, dy, dz

    """
    _ui_name = "MEG sensors"

    __tablename__ = None

    __mapper_args__ = {'polymorphic_identity': MEG_POLYMORPHIC_IDENTITY}

    sensors_type = types_basic.String(default=MEG_POLYMORPHIC_IDENTITY)

    orientations = arrays.OrientationArray(label="Sensor orientations",
                                           doc="An array representing the orientation of the MEG SQUIDs")

    has_orientation = types_basic.Bool(default=True, order=-1)


    @classmethod
    def from_file(cls, source_file="meg_151.txt.bz2", instance=None):
        result = super(SensorsMEG, cls).from_file(source_file, instance)

        source_full_path = try_get_absolute_path("tvb_data.sensors", source_file)
        reader = FileReader(source_full_path)
        result.orientations = reader.read_array(use_cols=(4, 5, 6))

        return result


class SensorsInternal(Sensors):
    """
    Sensors inside the brain...
    """
    _ui_name = "Internal Sensors"

    __tablename__ = None

    __mapper_args__ = {'polymorphic_identity': INTERNAL_POLYMORPHIC_IDENTITY}

    sensors_type = types_basic.String(default=INTERNAL_POLYMORPHIC_IDENTITY)


    @classmethod
    def from_file(cls, source_file="seeg_39.txt.bz2", instance=None):
        return super(SensorsInternal, cls).from_file(source_file, instance)