"""Type system, units, coordinates, names and deterministic random."""

import math
import random as pyrandom
import re
import shutil
import subprocess

import pytest

from nodebridge.common import coordinates as co
from nodebridge.common import names, units
from nodebridge.common.random import MODULUS, VEX_SOURCE, hash_int, random_float, random_range
from nodebridge.ir.types import Conversion, DataType, TypeRef, connection, conversion, convert_value


# --- types --------------------------------------------------------------------
@pytest.mark.parametrize(
    "source, target, expected",
    [
        (DataType.FLOAT, DataType.FLOAT, Conversion.IDENTITY),
        (DataType.FLOAT, DataType.VECTOR3, Conversion.IMPLICIT),
        (DataType.INT, DataType.FLOAT, Conversion.IMPLICIT),
        (DataType.VECTOR3, DataType.FLOAT, Conversion.LOSSY),
        (DataType.VECTOR3, DataType.ROTATION, Conversion.IMPLICIT),
        (DataType.MESH, DataType.GEOMETRY, Conversion.IDENTITY),
        (DataType.GEOMETRY, DataType.POINTS, Conversion.IMPLICIT),
        (DataType.MESH, DataType.CURVE, Conversion.INVALID),
        (DataType.GEOMETRY, DataType.FLOAT, Conversion.INVALID),
        (DataType.SHADER, DataType.COLOR, Conversion.INVALID),
        (DataType.MATERIAL, DataType.OBJECT, Conversion.INVALID),
    ],
)
def test_conversion_rules(source, target, expected):
    assert conversion(source, target) == expected


def test_field_cannot_flow_into_single_value_socket():
    assert connection(TypeRef(DataType.FLOAT, True), TypeRef(DataType.FLOAT), target_accepts_field=False) == Conversion.INVALID
    assert connection(TypeRef(DataType.FLOAT), TypeRef(DataType.FLOAT, True)) == Conversion.IDENTITY


def test_value_conversion_matches_blender():
    assert convert_value([1.0, 2.0, 3.0], DataType.VECTOR3, DataType.FLOAT) == 2.0
    assert convert_value(2.0, DataType.FLOAT, DataType.VECTOR3) == [2.0, 2.0, 2.0]
    assert convert_value(0.6, DataType.FLOAT, DataType.INT) == 1
    assert convert_value([0.2, 0.4, 0.6], DataType.VECTOR3, DataType.COLOR) == [0.2, 0.4, 0.6, 1.0]


# --- units --------------------------------------------------------------------
def test_length_and_density_units():
    assert units.convert_length(2.0, units.BLENDER_UNITS, units.UNREAL_UNITS) == pytest.approx(200.0)
    assert units.convert_length(2.0, units.BLENDER_UNITS, units.HOUDINI_UNITS) == pytest.approx(2.0)
    assert units.convert_length(1.0, units.BLENDER_UNITS, units.UNREAL_UNITS, scene_scale=0.01) == pytest.approx(1.0)
    # 10 points per square meter is 0.001 per square centimeter
    assert units.convert_area_density(10.0, units.BLENDER_UNITS, units.UNREAL_UNITS) == pytest.approx(0.001)


def test_angle_time_and_role_conversion():
    assert units.convert_angle(math.pi, units.AngleUnit.RADIANS, units.AngleUnit.DEGREES) == pytest.approx(180.0)
    assert units.convert_frame(25, 24, 30) == pytest.approx(31.0)
    assert units.convert_scalar([math.pi / 2, 0.0], units.ValueRole.EULER, units.BLENDER_UNITS, units.HOUDINI_UNITS) == [pytest.approx(90.0), 0.0]
    assert units.convert_scalar(3.0, units.ValueRole.FACTOR, units.BLENDER_UNITS, units.UNREAL_UNITS) == 3.0


# --- coordinates ----------------------------------------------------------------
def test_houdini_axes():
    assert co.convert_point((1, 2, 3), co.BLENDER, co.HOUDINI) == (1, 3, -2)
    assert co.convert_scale((1, 2, 3), co.BLENDER, co.HOUDINI) == (1, 3, 2)
    assert co.HOUDINI.determinant == pytest.approx(1.0)


def test_unreal_axes_are_left_handed():
    assert co.convert_point((1, 2, 3), co.BLENDER, co.UNREAL) == (1, -2, 3)
    assert co.UNREAL.determinant == pytest.approx(-1.0)
    assert co.convert_scale((1, 2, 3), co.BLENDER, co.UNREAL) == (1, 2, 3)


@pytest.mark.parametrize("order", ["XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX"])
def test_euler_roundtrip_all_orders(order):
    rng = pyrandom.Random(order)
    for _ in range(25):
        euler = [rng.uniform(-1.4, 1.4) for _ in range(3)]
        matrix = co.euler_to_matrix(euler, order)
        back = co.matrix_to_euler(matrix, order)
        assert back == pytest.approx(euler, abs=1e-9)


def test_blender_euler_equals_houdini_xzy_with_reordered_angles():
    """The SOP translator relies on: Blender XYZ (a, b, c) == Houdini rOrd xzy with r = (a, c, -b)."""
    rng = pyrandom.Random(7)
    for _ in range(20):
        a, b, c = (rng.uniform(-3, 3) for _ in range(3))
        expected = co.convert_rotation_matrix(co.euler_to_matrix((a, b, c), "XYZ"), co.BLENDER, co.HOUDINI)
        houdini = co.euler_to_matrix((a, c, -b), "XZY")
        for row_e, row_h in zip(expected, houdini):
            assert row_e == pytest.approx(row_h, abs=1e-9)


def test_unreal_rotator_roundtrip_and_yaw_sign():
    for pitch, yaw, roll in [(10, 20, 30), (-45, 170, 5), (80, -60, -120)]:
        assert co.matrix_to_unreal_rotator(co.unreal_rotator_to_matrix(pitch, yaw, roll)) == pytest.approx((pitch, yaw, roll), abs=1e-6)
    # Rotating +90 degrees about Blender Z is a -90 degree yaw in Unreal (mirrored Y axis).
    assert co.blender_euler_to_unreal_rotator((0, 0, math.pi / 2)) == pytest.approx((0.0, -90.0, 0.0), abs=1e-6)
    signs = co.unreal_axis_signs()
    assert signs["Z"] == ("yaw", -1.0)
    assert signs["X"][0] == "roll" and signs["Y"][0] == "pitch"


def test_quaternion_roundtrip_and_uv_conventions():
    matrix = co.euler_to_matrix((0.3, -0.7, 1.1))
    assert co.quaternion_to_matrix(co.matrix_to_quaternion(matrix))[0] == pytest.approx(matrix[0])
    assert co.convert_uv((0.25, 0.1), co.BLENDER, co.UNREAL) == (0.25, 0.9)
    assert co.convert_uv((0.25, 0.1), co.BLENDER, co.HOUDINI) == (0.25, 0.1)
    assert co.normal_map_green_flip_required(co.BLENDER, co.UNREAL)
    assert not co.normal_map_green_flip_required(co.BLENDER, co.HOUDINI)


def test_vex_coordinate_library_matches_python_basis():
    from nodebridge.backend.houdini.vexlib import COORDINATES

    assert "nb_h(vector b) { return set(b.x, b.z, -b.y); }" in COORDINATES
    assert co.convert_point((7, 8, 9), co.BLENDER, co.HOUDINI) == (7, 9, -8)
    assert co.convert_point((7, 9, -8), co.HOUDINI, co.BLENDER) == (7, 8, 9)


# --- names ------------------------------------------------------------------------
def test_names():
    assert names.houdini_node_name("Building Scatter") == "building_scatter"
    assert names.houdini_node_name("3 Floors") == "n_3_floors"
    assert names.unreal_asset_name("building scatter", "PCG_") == "PCG_BuildingScatter"
    assert names.python_identifier("import") == "import_"
    assert names.houdini_label_name("IN Geometry") == "IN_Geometry"
    allocator = names.NameAllocator()
    assert [allocator.allocate("box") for _ in range(3)] == ["box", "box_2", "box_3"]


# --- random -----------------------------------------------------------------------
def test_random_is_deterministic_and_in_range():
    values = [random_float(7, i) for i in range(2000)]
    assert values == [random_float(7, i) for i in range(2000)]
    assert all(0.0 <= v <= 1.0 for v in values)
    assert 0.45 < sum(values) / len(values) < 0.55
    assert len(set(round(v, 9) for v in values)) == len(values)
    assert random_float(7, 3) != random_float(8, 3)
    assert random_float(7, 3, stream=1) != random_float(7, 3, stream=0)
    assert 2.0 <= random_range(1, 2, 2.0, 5.0) <= 5.0
    assert 1 <= hash_int(0, 0) < MODULUS


def test_random_neighbouring_ids_are_decorrelated():
    a = [random_float(1, i) for i in range(500)]
    b = [random_float(1, i + 1) for i in range(500)]
    mean_a, mean_b = sum(a) / 500, sum(b) / 500
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / 500
    var = (sum((x - mean_a) ** 2 for x in a) / 500) ** 0.5 * (sum((y - mean_b) ** 2 for y in b) / 500) ** 0.5
    assert abs(cov / var) < 0.15


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not available")
def test_vex_random_library_matches_python(tmp_path):
    """Compile the generated VEX random library as C and compare with Python."""
    c_source = re.sub(r"\(([^()]*;[^()]*)\)\s*\{", lambda m: "(" + m.group(1).replace(";", ",") + ") {", VEX_SOURCE)
    program = tmp_path / "rnd.c"
    program.write_text(
        "#include <stdio.h>\n#include <stdlib.h>\n" + c_source + "\nint main(void){\n"
        "  int seeds[3] = {0, 7, 123456};\n"
        "  for (int s = 0; s < 3; s++) for (int id = 0; id < 50; id++) for (int st = 0; st < 3; st++)\n"
        '    printf("%d %.9f\\n", nb_hash(seeds[s], id, st), nb_random(seeds[s], id, st));\n'
        "  return 0;\n}\n"
    )
    binary = tmp_path / "rnd"
    subprocess.run(["gcc", "-std=c99", "-O1", str(program), "-o", str(binary)], check=True)
    lines = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout.split("\n")
    index = 0
    for seed in (0, 7, 123456):
        for element in range(50):
            for stream in range(3):
                hashed, value = lines[index].split()
                assert int(hashed) == hash_int(seed, element, stream)
                # nb_random returns a 32-bit float, as VEX does.
                assert float(value) == pytest.approx(random_float(seed, element, stream), abs=1e-6)
                index += 1
