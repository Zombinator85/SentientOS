import emotion_memory as em


def test_average_emotion():
    em.clear()
    em.add_emotion({'Joy': 1.0})
    em.add_emotion({'Anger': 0.5})
    avg = em.average_emotion()
    assert avg['Joy'] > 0
    assert avg['Anger'] > 0
