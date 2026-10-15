from nodebridge.common.names import sanitize_identifier, unique_name


def test_source_labels_become_safe_identifiers():
    assert sanitize_identifier("Building Scatter") == "building_scatter"
    assert sanitize_identifier("123 Door") == "n_123_door"
    assert sanitize_identifier("   ") == "node"


def test_unique_name_avoids_collisions():
    used: set[str] = set()
    assert unique_name("Cube", used) == "cube"
    assert unique_name("Cube", used) == "cube_2"
