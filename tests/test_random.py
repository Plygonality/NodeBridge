from nodebridge.common.random import hash32, random01, random_range, random_vector, vex_random_library


def test_hash_is_stable_and_depends_on_both_inputs():
    assert hash32(7, 3) == hash32(7, 3)
    assert hash32(7, 3) != hash32(8, 3)
    assert hash32(7, 3) != hash32(7, 4)
    assert hash32(7, 3) == 1405751739


def test_random_range_and_vector_stay_inside_bounds():
    value = random_range(1, 9, -2.0, 4.0)
    assert -2.0 <= value < 4.0
    vector = random_vector(4, 2, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    assert len(vector) == 3
    assert all(0.0 <= component < 1.0 for component in vector)
    assert len({random01(1, index) for index in range(8)}) > 1


def test_vex_library_uses_the_same_mix_constants():
    source = vex_random_library()
    assert "747796405" in source
    assert "-1403630843" in source
    assert "-2048144777" in source
    assert "-1028477379" in source
    assert "nb_rand" in source
