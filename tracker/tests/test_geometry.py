from tracker.utils.geometry import bbox_to_center, distance


def test_bbox_to_center():
    assert bbox_to_center((0, 0, 10, 20)) == (5.0, 10.0)


def test_distance():
    assert distance((0, 0), (3, 4)) == 5.0
